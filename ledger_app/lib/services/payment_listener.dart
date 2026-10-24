// lib/services/payment_listener.dart
//
// Flutter 侧的通道封装：
//  - MethodChannel "ledger/notify"：hasPermission / openSettings
//  - EventChannel  "ledger/events"：接收 Kotlin 服务推上来的通知事件
//
// 通道名必须与 MainActivity.kt / PaymentNotificationService.kt 里完全一致。

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// 一条来自微信 / 支付宝的通知事件（Kotlin 侧原样透传）
class PaymentEvent {
  const PaymentEvent({
    required this.source,
    required this.packageName,
    required this.title,
    required this.text,
    required this.bigText,
    required this.lines,
    required this.raw,
    required this.timestamp,
  });

  /// 'wechat' 或 'alipay'
  final String source;

  /// 原始包名，如 com.tencent.mm
  final String packageName;

  final String title;
  final String text;
  final String bigText;

  /// EXTRA_TEXT_LINES 展开的多行文本
  final List<String> lines;

  /// 上面几段拼起来的原始文本，调试用
  final String raw;

  /// 通知的 postTime（毫秒时间戳）
  final int timestamp;

  String get sourceLabel {
    switch (source) {
      case 'wechat':
        return '微信';
      case 'alipay':
        return '支付宝';
      default:
        return source;
    }
  }

  factory PaymentEvent.fromMap(Map<dynamic, dynamic> map) {
    final rawLines = map['lines'];
    final lines = <String>[];
    if (rawLines is List) {
      for (final item in rawLines) {
        if (item != null) lines.add(item.toString());
      }
    }

    final rawTs = map['timestamp'];
    int timestamp;
    if (rawTs is int) {
      timestamp = rawTs;
    } else if (rawTs is num) {
      timestamp = rawTs.toInt();
    } else {
      timestamp = DateTime.now().millisecondsSinceEpoch;
    }

    String str(Object? v) => v is String ? v : (v == null ? '' : v.toString());

    return PaymentEvent(
      source: str(map['source']),
      packageName: str(map['packageName']),
      title: str(map['title']),
      text: str(map['text']),
      bigText: str(map['bigText']),
      lines: lines,
      raw: str(map['raw']),
      timestamp: timestamp,
    );
  }

  @override
  String toString() =>
      'PaymentEvent(source: $source, timestamp: $timestamp, raw: $raw)';
}

class PaymentListener {
  PaymentListener._();

  static const MethodChannel _method = MethodChannel('ledger/notify');
  static const EventChannel _event = EventChannel('ledger/events');

  /// 缓存一份流：EventChannel.receiveBroadcastStream 每次调用都会重新向原生订阅，
  /// 这里只订阅一次，多个页面共用。
  static Stream<PaymentEvent>? _stream;

  /// 原生通知事件流（广播流）
  static Stream<PaymentEvent> stream() {
    _stream ??= _event
        .receiveBroadcastStream()
        .map<PaymentEvent?>((dynamic event) {
          if (event is Map) {
            try {
              return PaymentEvent.fromMap(event);
            } catch (e) {
              debugPrint('PaymentEvent 解析失败: $e');
              return null;
            }
          }
          return null;
        })
        .where((PaymentEvent? e) => e != null)
        .cast<PaymentEvent>();
    return _stream!;
  }

  /// 是否已授予"通知使用权"（NotificationListenerService 绑定状态）
  static Future<bool> hasPermission() async {
    try {
      final granted = await _method.invokeMethod<bool>('hasPermission');
      return granted ?? false;
    } on MissingPluginException {
      debugPrint('ledger/notify 通道未注册（非 Android 平台？）');
      return false;
    } on PlatformException catch (e) {
      debugPrint('hasPermission 调用失败: ${e.code} ${e.message}');
      return false;
    }
  }

  /// 跳转到系统的"通知使用权"设置页
  static Future<bool> openSettings() async {
    try {
      final ok = await _method.invokeMethod<bool>('openSettings');
      return ok ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException catch (e) {
      debugPrint('openSettings 调用失败: ${e.code} ${e.message}');
      return false;
    }
  }
}
