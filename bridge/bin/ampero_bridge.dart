import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:isolate';

import 'package:ffi/ffi.dart';

const int requestFlag = 0x11;
const int sendFlag = 0x12;
const int currentSceneAddress = 0x03000001;
const int slotModelAddress = 0x01040002;

typedef ScanCallbackNative = Void Function(Pointer<Int32>, Int32);
typedef ReceiveCallbackNative = Void Function(
  Pointer<Void>,
  Uint32,
  Pointer<Void>,
  Uint32,
  Int32,
);
typedef StateCallbackNative = Void Function(Pointer<Void>, Int32);
typedef SendCallbackNative = Void Function(
  Pointer<Void>,
  Int32,
  Int32,
  Int32,
);

typedef InitDartApiNative = IntPtr Function(Pointer<Void>);
typedef InitDartApiDart = int Function(Pointer<Void>);
typedef ScanNative = Void Function(
  Pointer<Utf8>,
  Pointer<NativeFunction<ScanCallbackNative>>,
);
typedef ScanDart = void Function(
  Pointer<Utf8>,
  Pointer<NativeFunction<ScanCallbackNative>>,
);
typedef ConnectNative = Pointer<Void> Function(
  Int32,
  Int32,
  Pointer<Utf8>,
  Pointer<NativeFunction<ReceiveCallbackNative>>,
  Pointer<NativeFunction<StateCallbackNative>>,
  Pointer<NativeFunction<SendCallbackNative>>,
);
typedef ConnectDart = Pointer<Void> Function(
  int,
  int,
  Pointer<Utf8>,
  Pointer<NativeFunction<ReceiveCallbackNative>>,
  Pointer<NativeFunction<StateCallbackNative>>,
  Pointer<NativeFunction<SendCallbackNative>>,
);
typedef RegisterPortNative = Void Function(Pointer<Void>, Int64);
typedef RegisterPortDart = void Function(Pointer<Void>, int);
typedef SendMessageNative = Int32 Function(
  Pointer<Void>,
  Int32,
  Pointer<Void>,
  Int32,
  Int32,
);
typedef SendMessageDart = int Function(
  Pointer<Void>,
  int,
  Pointer<Void>,
  int,
  int,
);
typedef TimerCallbackNative = Void Function(Pointer<Void>, Int32);
typedef TimerCallbackDart = void Function(Pointer<Void>, int);
typedef DisconnectNative = Void Function(Pointer<Void>);
typedef DisconnectDart = void Function(Pointer<Void>);

AmperoBridge? _activeBridge;

@pragma('vm:entry-point')
void _scanInputCallback(Pointer<Int32> data, int size) {
  _activeBridge?._completeScan(true, data, size);
}

@pragma('vm:entry-point')
void _scanOutputCallback(Pointer<Int32> data, int size) {
  _activeBridge?._completeScan(false, data, size);
}

@pragma('vm:entry-point')
void _receiveCallback(
  Pointer<Void> device,
  int address,
  Pointer<Void> data,
  int dataSize,
  int flag,
) {
  final bytes = dataSize > 0
      ? List<int>.from(data.cast<Uint8>().asTypedList(dataSize))
      : <int>[];
  _activeBridge?._completeMessage(
    DeviceMessage(address: address, data: bytes, flag: flag),
  );
}

@pragma('vm:entry-point')
void _stateCallback(Pointer<Void> device, int state) {
  _activeBridge?._states.add(state);
}

@pragma('vm:entry-point')
void _sendCallback(
  Pointer<Void> device,
  int messageId,
  int event,
  int address,
) {
  _activeBridge?._sendEvents.add({
    'message_id': messageId,
    'event': event,
    'address': address,
  });
}

class DeviceMessage {
  DeviceMessage(
      {required this.address, required this.data, required this.flag});

  final int address;
  final List<int> data;
  final int flag;
}

class AmperoBridge {
  AmperoBridge(String dllPath)
      : _initDartApi = DynamicLibrary.open(dllPath)
            .lookupFunction<InitDartApiNative, InitDartApiDart>(
                'InitDartApiDL'),
        _scanInput = DynamicLibrary.open(dllPath)
            .lookupFunction<ScanNative, ScanDart>('scanInDevice'),
        _scanOutput = DynamicLibrary.open(dllPath)
            .lookupFunction<ScanNative, ScanDart>('scanOutDevice'),
        _connect = DynamicLibrary.open(dllPath)
            .lookupFunction<ConnectNative, ConnectDart>('connectDevice'),
        _registerPort = DynamicLibrary.open(dllPath)
            .lookupFunction<RegisterPortNative, RegisterPortDart>(
                'registerSendPort'),
        _send = DynamicLibrary.open(dllPath)
            .lookupFunction<SendMessageNative, SendMessageDart>(
                'sendMidiMessage'),
        _timerCallback = DynamicLibrary.open(dllPath)
            .lookupFunction<TimerCallbackNative, TimerCallbackDart>(
                'timerCallback'),
        _disconnect = DynamicLibrary.open(dllPath)
            .lookupFunction<DisconnectNative, DisconnectDart>(
                'disConnectDevice');

  final InitDartApiDart _initDartApi;
  final ScanDart _scanInput;
  final ScanDart _scanOutput;
  final ConnectDart _connect;
  final RegisterPortDart _registerPort;
  final SendMessageDart _send;
  final TimerCallbackDart _timerCallback;
  final DisconnectDart _disconnect;

  final StreamController<int> _states = StreamController<int>.broadcast();
  final StreamController<Map<String, int>> _sendEvents =
      StreamController<Map<String, int>>.broadcast();
  final Map<int, List<Completer<DeviceMessage>>> _pending = {};

  Completer<List<int>>? _inputScan;
  Completer<List<int>>? _outputScan;
  Pointer<Void> _device = nullptr;
  ReceivePort? _receivePort;
  StreamSubscription<dynamic>? _portSubscription;
  Timer? _pumpTimer;

  Future<void> initialize() async {
    _activeBridge = this;
    final result = _initDartApi(NativeApi.initializeApiDLData);
    if (result != 0) {
      throw StateError('InitDartApiDL failed with code $result');
    }
    _pumpTimer = Timer.periodic(const Duration(milliseconds: 30), (_) {
      _timerCallback(nullptr, 9);
      if (_device != nullptr) {
        _timerCallback(_device, 0);
      }
    });
  }

  Future<Map<String, List<int>>> scan(String deviceName) async {
    _inputScan = Completer<List<int>>();
    _outputScan = Completer<List<int>>();
    final name = deviceName.toNativeUtf8();
    try {
      _scanInput(name, Pointer.fromFunction(_scanInputCallback));
      _scanOutput(name, Pointer.fromFunction(_scanOutputCallback));
      return {
        'inputs': await _inputScan!.future.timeout(const Duration(seconds: 3)),
        'outputs':
            await _outputScan!.future.timeout(const Duration(seconds: 3)),
      };
    } finally {
      calloc.free(name);
    }
  }

  Future<void> connect(int inputIndex, int outputIndex) async {
    _receivePort = ReceivePort();
    _portSubscription = _receivePort!.listen(_handleNativeMessage);
    final productId = '97'.toNativeUtf8();
    try {
      _device = _connect(
        inputIndex,
        outputIndex,
        productId,
        Pointer.fromFunction(_receiveCallback),
        Pointer.fromFunction(_stateCallback),
        Pointer.fromFunction(_sendCallback),
      );
    } finally {
      calloc.free(productId);
    }
    if (_device == nullptr) {
      throw StateError('connectDevice returned nullptr');
    }
    _registerPort(_device, _receivePort!.sendPort.nativePort);
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }

  Future<DeviceMessage> request(
    int address, {
    List<int> payload = const [],
    Duration timeout = const Duration(seconds: 3),
  }) async {
    if (_device == nullptr) {
      throw StateError('device is not connected');
    }
    final completer = Completer<DeviceMessage>();
    _pending.putIfAbsent(address, () => []).add(completer);
    Pointer<Uint8> data = nullptr;
    if (payload.isNotEmpty) {
      data = calloc<Uint8>(payload.length);
      data.asTypedList(payload.length).setAll(0, payload);
    }
    try {
      final messageId = _send(
        _device,
        address,
        data.cast<Void>(),
        payload.length,
        requestFlag,
      );
      if (messageId < 0) {
        throw StateError('sendMidiMessage failed with $messageId');
      }
      return await completer.future.timeout(timeout);
    } finally {
      if (data != nullptr) {
        calloc.free(data);
      }
      _pending[address]?.remove(completer);
    }
  }

  int sendMessage(
    int address, {
    List<int> payload = const [],
    int flag = sendFlag,
  }) {
    if (_device == nullptr) {
      throw StateError('device is not connected');
    }
    Pointer<Uint8> data = nullptr;
    if (payload.isNotEmpty) {
      data = calloc<Uint8>(payload.length);
      data.asTypedList(payload.length).setAll(0, payload);
    }
    try {
      final messageId = _send(
        _device,
        address,
        data.cast<Void>(),
        payload.length,
        flag,
      );
      if (messageId < 0) {
        throw StateError('sendMidiMessage failed with $messageId');
      }
      return messageId;
    } finally {
      if (data != nullptr) {
        calloc.free(data);
      }
    }
  }

  void _handleNativeMessage(dynamic message) {
    if (message is! List || message.length < 4) {
      return;
    }
    final nativeType = message[0] as int;
    if (nativeType == 0) {
      final callback = Pointer<NativeFunction<StateCallbackNative>>.fromAddress(
        message[1] as int,
      ).asFunction<void Function(Pointer<Void>, int)>();
      callback(Pointer<Void>.fromAddress(message[2] as int), message[3] as int);
      return;
    }
    if (nativeType == 1 && message.length >= 7) {
      final callback =
          Pointer<NativeFunction<ReceiveCallbackNative>>.fromAddress(
        message[1] as int,
      ).asFunction<
              void Function(Pointer<Void>, int, Pointer<Void>, int, int)>();
      callback(
        Pointer<Void>.fromAddress(message[2] as int),
        message[3] as int,
        Pointer<Void>.fromAddress(message[4] as int),
        message[5] as int,
        message[6] as int,
      );
      return;
    }
  }

  void _completeScan(bool input, Pointer<Int32> data, int size) {
    final values = data != nullptr && size > 0
        ? List<int>.from(data.asTypedList(size))
        : <int>[];
    final completer = input ? _inputScan : _outputScan;
    if (completer != null && !completer.isCompleted) {
      completer.complete(values);
    }
  }

  void _completeMessage(DeviceMessage message) {
    final pending = _pending[message.address];
    if (pending != null && pending.isNotEmpty && !pending.first.isCompleted) {
      pending.first.complete(message);
    }
  }

  Future<void> close() async {
    _pumpTimer?.cancel();
    if (_device != nullptr) {
      _disconnect(_device);
      _device = nullptr;
    }
    await _portSubscription?.cancel();
    _receivePort?.close();
    await _states.close();
    await _sendEvents.close();
    _activeBridge = null;
  }
}

int _readSignedLittleEndian(List<int> bytes) {
  var value = 0;
  for (var index = 0; index < bytes.length; index++) {
    value |= bytes[index] << (8 * index);
  }
  final signBit = 1 << (bytes.length * 8 - 1);
  if ((value & signBit) != 0) {
    value -= 1 << (bytes.length * 8);
  }
  return value;
}

List<int> _hexToBytes(String value) {
  final normalized = value.replaceAll(RegExp(r'\s+'), '');
  if (normalized.isEmpty) {
    return <int>[];
  }
  if (normalized.length.isOdd) {
    throw FormatException('hex payload length must be even');
  }
  return [
    for (var index = 0; index < normalized.length; index += 2)
      int.parse(normalized.substring(index, index + 2), radix: 16),
  ];
}

String _bytesToHex(List<int> bytes) =>
    bytes.map((value) => value.toRadixString(16).padLeft(2, '0')).join(' ');

Future<void> _serve(AmperoBridge bridge, Map<String, List<int>> scan) async {
  stdout.writeln('AMPERO_READY:${jsonEncode({'ok': true, 'scan': scan})}');
  await stdout.flush();
  await for (final line
      in stdin.transform(utf8.decoder).transform(const LineSplitter())) {
    if (line.trim().isEmpty) {
      continue;
    }
    dynamic decoded;
    try {
      decoded = jsonDecode(line);
      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('request must be a JSON object');
      }
      final id = decoded['id'];
      final operation = decoded['op'];
      if (operation == 'request') {
        final address = decoded['address'] as int;
        final timeoutMs = (decoded['timeout_ms'] as int?) ?? 2000;
        final message = await bridge.request(
          address,
          payload: _hexToBytes((decoded['data_hex'] as String?) ?? ''),
          timeout: Duration(milliseconds: timeoutMs),
        );
        stdout.writeln(
          'AMPERO_RESPONSE:${jsonEncode({
                'id': id,
                'ok': true,
                'address': message.address,
                'flag': message.flag,
                'data': message.data,
                'data_hex': _bytesToHex(message.data),
              })}',
        );
      } else if (operation == 'send') {
        final messageId = bridge.sendMessage(
          decoded['address'] as int,
          payload: _hexToBytes((decoded['data_hex'] as String?) ?? ''),
          flag: (decoded['flag'] as int?) ?? sendFlag,
        );
        stdout.writeln(
          'AMPERO_RESPONSE:${jsonEncode({
                'id': id,
                'ok': true,
                'message_id': messageId,
              })}',
        );
      } else if (operation == 'close') {
        stdout.writeln(
          'AMPERO_RESPONSE:${jsonEncode({'id': id, 'ok': true})}',
        );
        await stdout.flush();
        return;
      } else {
        throw FormatException('unsupported operation: $operation');
      }
    } catch (error, stackTrace) {
      final id = decoded is Map<String, dynamic> ? decoded['id'] : null;
      stdout.writeln(
        'AMPERO_RESPONSE:${jsonEncode({
              'id': id,
              'ok': false,
              'error': error.toString(),
              'stack': stackTrace.toString(),
            })}',
      );
    }
    await stdout.flush();
  }
}

Future<void> main(List<String> arguments) async {
  if (arguments.length < 2 ||
      !{'probe-scene', 'probe-slot', 'serve'}.contains(arguments.first)) {
    stderr.writeln(
      'usage: ampero_bridge probe-scene DLL_PATH | '
      'probe-slot DLL_PATH SLOT_ID | serve DLL_PATH',
    );
    exitCode = 64;
    return;
  }
  final bridge = AmperoBridge(arguments[1]);
  try {
    await bridge.initialize();
    final scan = await bridge.scan('Ampero II Stomp');
    if (scan['inputs']!.isEmpty || scan['outputs']!.isEmpty) {
      throw StateError('Ampero II Stomp MIDI ports were not found: $scan');
    }
    await bridge.connect(scan['inputs']!.last, scan['outputs']!.last);
    if (arguments.first == 'serve') {
      await _serve(bridge, scan);
      return;
    }
    final isSlotProbe = arguments.first == 'probe-slot';
    if (isSlotProbe && arguments.length < 3) {
      throw ArgumentError('probe-slot requires SLOT_ID');
    }
    final slotId = isSlotProbe ? int.parse(arguments[2]) : null;
    final message = await bridge.request(
      isSlotProbe ? slotModelAddress : currentSceneAddress,
      payload: isSlotProbe ? [slotId!] : const [],
    );
    final result = <String, dynamic>{
      'ok': true,
      'scan': scan,
      'address': '0x${message.address.toRadixString(16).padLeft(8, '0')}',
      'flag': message.flag,
      'data': message.data,
      'data_hex': message.data
          .map((value) => value.toRadixString(16).padLeft(2, '0'))
          .join(' '),
    };
    if (isSlotProbe && message.data.length >= 7) {
      result['slot'] = _readSignedLittleEndian(message.data.sublist(0, 1));
      result['category_id'] =
          _readSignedLittleEndian(message.data.sublist(1, 2));
      result['model_code'] =
          _readSignedLittleEndian(message.data.sublist(2, 6));
      result['enabled'] = message.data[6] != 0;
    } else if (message.data.length >= 4) {
      result['scene'] = _readSignedLittleEndian(message.data.sublist(0, 2));
      result['is_empty'] = _readSignedLittleEndian(message.data.sublist(2, 4));
    }
    stdout.writeln('AMPERO_JSON:${jsonEncode(result)}');
  } catch (error, stackTrace) {
    stdout.writeln(
      'AMPERO_JSON:${jsonEncode({
            'ok': false,
            'error': error.toString(),
            'stack': stackTrace.toString()
          })}',
    );
    exitCode = 1;
  } finally {
    await bridge.close();
  }
}
