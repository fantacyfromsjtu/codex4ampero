import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

from . import __version__
from .catalog import EffectCatalog
from .constants import Command, MessageFlag
from .controller import DeviceController, prepare_plan
from .dart_bridge import DartBridgeTransport
from .errors import AmperoError
from .installation import locate_editor
from .native import NativeTransport
from .plan import TonePlan
from .preset_save import prepare_preset_save


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex4ampero",
        description="Safe local control layer for HOTONE Ampero II Stomp",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--editor-dir", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="check installation and DLL loading")
    doctor.add_argument("--scan", action="store_true", help="also enumerate device ports")

    device = subparsers.add_parser("device", help="device operations")
    device_subparsers = device.add_subparsers(dest="device_command", required=True)
    device_subparsers.add_parser("scan", help="enumerate matching MIDI ports")
    snapshot = device_subparsers.add_parser(
        "snapshot", help="read current slot models and optionally their parameters"
    )
    snapshot.add_argument("--slots", type=int, default=12)
    snapshot.add_argument("--include-parameters", action="store_true")
    snapshot.add_argument("--timeout", type=float, default=1.5)
    routing = device_subparsers.add_parser(
        "routing", help="read the current routing template without a full preset snapshot"
    )
    routing.add_argument("--timeout", type=float, default=5.0)
    device_subparsers.add_parser(
        "handshake", help="run fixed read-only connection-state diagnostics"
    )

    catalog = subparsers.add_parser("catalog", help="query the installed effect catalog")
    catalog_subparsers = catalog.add_subparsers(dest="catalog_command", required=True)
    search = catalog_subparsers.add_parser("search", help="search effects")
    search.add_argument("query")
    search.add_argument("--category")
    search.add_argument("--limit", type=int, default=20)
    show = catalog_subparsers.add_parser("show", help="show one exact effect")
    show.add_argument("name")
    show.add_argument("--category")

    plan = subparsers.add_parser("plan", help="validate, preview, or apply a tone plan")
    plan_subparsers = plan.add_subparsers(dest="plan_command", required=True)
    for command in ("validate", "preview"):
        plan_parser = plan_subparsers.add_parser(command)
        plan_parser.add_argument("path", type=Path)
    apply_parser = plan_subparsers.add_parser("apply")
    apply_parser.add_argument("path", type=Path)
    apply_parser.add_argument("--execute", action="store_true")
    apply_parser.add_argument("--confirm")
    apply_parser.add_argument(
        "--confirm-device-patch",
        help=(
            "exact patch label shown on the hardware display; used only when the device "
            "protocol explicitly returns 0xffff for the current patch index"
        ),
    )
    apply_parser.add_argument("--allow-unverified-reads", action="store_true")
    apply_parser.add_argument("--journal", type=Path)
    rollback = plan_subparsers.add_parser("rollback")
    rollback.add_argument("journal", type=Path)
    rollback.add_argument("--execute", action="store_true")
    rollback.add_argument("--confirm")
    save = plan_subparsers.add_parser(
        "save", help="save a verified applied live buffer to its exact target patch"
    )
    save.add_argument("journal", type=Path)
    save.add_argument("--name", required=True)
    save.add_argument("--execute", action="store_true")
    save.add_argument("--confirm")
    save.add_argument("--save-journal", type=Path)
    return parser


def main(argv: Optional[list] = None) -> int:
    _configure_console_encoding()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        installation = locate_editor(args.editor_dir)
        if args.command == "doctor":
            return _doctor(args, installation)
        if args.command == "device":
            return _device(args, installation)
        catalog = EffectCatalog.from_installation(installation)
        if args.command == "catalog":
            return _catalog(args, catalog)
        if args.command == "plan":
            return _plan(args, installation, catalog)
        parser.error("unsupported command")
    except (AmperoError, FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as error:
        _emit(
            {"ok": False, "error": type(error).__name__, "message": str(error)},
            args.json_output,
        )
        return 2
    return 0


def _doctor(args, installation) -> int:
    with NativeTransport(installation) as transport:
        result = {
            "ok": True,
            "version": __version__,
            "installation": {
                "root": str(installation.root),
                "executable": str(installation.executable),
                "native_library": str(installation.native_library),
                "catalog_directory": str(installation.catalog_directory),
            },
            "native": transport.diagnostics,
            "bridge": DartBridgeTransport(installation).diagnostics,
        }
        if args.scan:
            result["scan"] = transport.scan()
    _emit(result, args.json_output)
    return 0


def _device(args, installation) -> int:
    if args.device_command == "scan":
        with NativeTransport(installation) as transport:
            scan = transport.scan()
        _emit({"ok": True, "scan": scan}, args.json_output)
        return 0
    if args.device_command == "snapshot":
        if not 1 <= args.slots <= 12:
            raise ValueError("--slots must be between 1 and 12")
        if not 0.1 <= args.timeout <= 10:
            raise ValueError("--timeout must be between 0.1 and 10 seconds")
        catalog = EffectCatalog.from_installation(installation)
        controller = DeviceController(installation, catalog)
        result = controller.snapshot(
            slot_count=args.slots,
            include_parameters=args.include_parameters,
            timeout=args.timeout,
        )
        _emit({"ok": True, "snapshot": result}, args.json_output)
        return 0
    if args.device_command == "routing":
        if not 0.1 <= args.timeout <= 10:
            raise ValueError("--timeout must be between 0.1 and 10 seconds")
        catalog = EffectCatalog.from_installation(installation)
        controller = DeviceController(installation, catalog)
        result = controller.routing(timeout=args.timeout)
        _emit({"ok": True, "routing": result}, args.json_output)
        return 0
    if args.device_command == "handshake":
        with DartBridgeTransport(installation) as transport:
            transport.connect()
            transport.send(int(Command.SCREEN_LOCK), b"", MessageFlag.REQUEST)
            time.sleep(0.1)
            for _ in range(5):
                transport.send(
                    int(Command.SOFTWARE_STATE), b"", MessageFlag.REQUEST
                )
                time.sleep(0.2)
            index_result = None
            index_error = None
            try:
                response = transport.request(int(Command.PRESET_INDEX), timeout=2.0)
                index_result = {
                    "data_hex": response.data.hex(" "),
                    "flag": response.flag,
                }
            except AmperoError as error:
                index_error = {"error": type(error).__name__, "message": str(error)}
            trace = transport.diagnostics_trace()
        _emit(
            {
                "ok": True,
                "index_result": index_result,
                "index_error": index_error,
                "trace": trace,
            },
            args.json_output,
        )
        return 0
    raise ValueError(f"unsupported device command: {args.device_command}")


def _catalog(args, catalog: EffectCatalog) -> int:
    if args.catalog_command == "search":
        effects = catalog.search(
            args.query, category=args.category, limit=max(1, min(args.limit, 100))
        )
        _emit(
            {
                "ok": True,
                "source": str(catalog.source),
                "count": len(effects),
                "effects": [effect.to_dict() for effect in effects],
            },
            args.json_output,
        )
        return 0
    if args.catalog_command == "show":
        effect = catalog.find_exact(args.name, args.category)
        _emit(
            {
                "ok": True,
                "source": str(catalog.source),
                "effect": effect.to_dict(include_description=True),
            },
            args.json_output,
        )
        return 0
    raise ValueError(f"unsupported catalog command: {args.catalog_command}")


def _plan(args, installation, catalog: EffectCatalog) -> int:
    controller = DeviceController(installation, catalog)
    if args.plan_command == "save":
        prepared = prepare_preset_save(args.journal, args.name)
        preview = {
            "ok": True,
            "mode": "preview",
            "save": prepared.to_dict(),
        }
        if not args.execute:
            preview["notice"] = (
                "No preset was saved. Re-run with --execute --confirm "
                f"{prepared.confirmation_token} only after the user approves this exact "
                "irreversible save preview."
            )
            _emit(preview, args.json_output)
            return 0
        if args.confirm != prepared.confirmation_token:
            raise ValueError(
                "preset save requires the exact confirmation token "
                f"{prepared.confirmation_token}"
            )
        save_journal_path = args.save_journal or _default_save_journal_path()
        result = controller.save_preset(prepared, journal_path=save_journal_path)
        _emit(
            {
                "ok": True,
                "save_journal_path": str(save_journal_path.resolve()),
                "result": result,
            },
            args.json_output,
        )
        return 0
    if args.plan_command in ("validate", "preview", "apply"):
        plan = TonePlan.from_file(args.path)
        prepared = prepare_plan(plan, catalog)
        if args.plan_command == "validate":
            _emit(
                {
                    "ok": True,
                    "valid": True,
                    "title": plan.title,
                    "safety": prepared.safety.to_dict(),
                },
                args.json_output,
            )
            return 0
        if args.plan_command == "preview" or not args.execute:
            result = {"ok": True, "mode": "preview", **prepared.to_dict()}
            if args.plan_command == "apply":
                result["notice"] = (
                    "No hardware changes were made. Add --execute --confirm APPLY "
                    "only after the user has approved this exact preview."
                )
            _emit(result, args.json_output)
            return 0
        if args.confirm != "APPLY":
            raise ValueError("hardware execution requires --confirm APPLY")
        journal_path = args.journal or _default_journal_path()
        result = controller.apply(
            prepared,
            journal_path=journal_path,
            allow_unverified_reads=args.allow_unverified_reads,
            confirmed_device_patch=args.confirm_device_patch,
        )
        _emit(
            _build_apply_response(plan, journal_path, result),
            args.json_output,
        )
        return 0
    if args.plan_command == "rollback":
        if not args.execute or args.confirm != "ROLLBACK":
            _emit(
                {
                    "ok": True,
                    "mode": "preview",
                    "journal_path": str(args.journal),
                    "notice": (
                        "No hardware changes were made. Add --execute --confirm ROLLBACK "
                        "after reviewing the journal."
                    ),
                },
                args.json_output,
            )
            return 0
        result = controller.rollback(args.journal)
        _emit({"ok": True, "result": result}, args.json_output)
        return 0
    raise ValueError(f"unsupported plan command: {args.plan_command}")


def _default_journal_path() -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / ".ampero_journals" / f"{timestamp}.journal.json"


def _build_apply_response(plan: TonePlan, journal_path: Path, result: dict) -> dict:
    response = {
        "ok": True,
        "journal_path": str(journal_path.resolve()),
        "result": result,
    }
    if plan.save_preview_name:
        save_preview = prepare_preset_save(journal_path, plan.save_preview_name)
        response["save_preview"] = save_preview.to_dict()
        response["save_notice"] = (
            "Tone changes were applied, but the preset was not saved. The exact "
            "journal-bound save preview is included so the user can respond with "
            f"{save_preview.confirmation_token} or decline saving."
        )
    return response


def _default_save_journal_path() -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / ".ampero_journals" / f"{timestamp}.save.journal.json"


def _emit(value: dict, json_output: bool) -> None:
    if json_output:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    if value.get("ok") is False:
        print(f"ERROR: {value.get('message')}", file=sys.stderr)
        return
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
