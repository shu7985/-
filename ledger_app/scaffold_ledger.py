#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scaffold_ledger.py —— 记账本 Flutter 安卓工程一键生成脚本

作用：在当前目录（或 --out 指定目录）下创建完整项目结构，并写入全部源码，
      生成后可直接 flutter pub get && flutter run。

本脚本是**自包含**的：所有文件内容都内联在下面的 FILES 字典里，
不需要联网、不需要额外依赖，只用 Python 3.7+ 标准库。

用法：
    python scaffold_ledger.py                 # 生成到当前目录，已存在的文件跳过
    python scaffold_ledger.py --out myapp     # 生成到 ./myapp
    python scaffold_ledger.py --force         # 覆盖已存在文件（会先备份成 .bak）
    python scaffold_ledger.py --list          # 只打印将要写出的文件清单
    python scaffold_ledger.py --clean         # 删除本脚本写出的文件（谨慎）

生成后的步骤：
    flutter create --org com.example --project-name ledger --platforms=android .
    # 注意顺序：先 create 生成 android 平台壳，再跑本脚本 --force 覆盖业务代码；
    # 如果本脚本先跑，flutter create 会补上缺失的 gradle wrapper / res / 图标，不冲突。

    或者直接：flutter pub get && flutter run
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_NAME = "ledger"

FILES: 'dict[str, str]' = {
    # ----------------------------------------------------------------------
    'pubspec.yaml': r'''# pubspec.yaml
name: ledger
description: "离线记账本：手动记账 + 微信/支付宝通知自动记账（数据只存本机）"
publish_to: 'none'
version: 1.0.0+1

environment:
  sdk: '>=3.0.0 <4.0.0'
  flutter: '>=3.10.0'

dependencies:
  flutter:
    sdk: flutter
  # 唯一第三方依赖：本机键值存储
  shared_preferences: ^2.2.3
  # 说明：flutter_localizations 是 Flutter SDK 自带包（非第三方），只是为了让
  # showDatePicker / Material 组件显示中文。若你要严格只保留 shared_preferences，
  # 删掉这 3 行 + main.dart 里的 localizationsDelegates/locale，日期选择器会变英文。
  flutter_localizations:
    sdk: flutter

dev_dependencies:
  flutter_test:
    sdk: flutter
  # ^3.0.0 对 Dart 3.0/3.1 都兼容；如果你的 Flutter 很新也可以升到 ^5.0.0
  flutter_lints: ^3.0.0

flutter:
  uses-material-design: true
  # TODO: 如需 App 图标，把图标放 assets/ 再在这里声明，或用 flutter_launcher_icons
''',
    # ----------------------------------------------------------------------
    'lib/main.dart': r'''// lib/main.dart
//
// App 入口。Material 3 + colorSchemeSeed = 0xFF007AFF（全局蓝色主题）。

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'screens/home_page.dart';

void main() {
  runApp(const LedgerApp());
}

class LedgerApp extends StatelessWidget {
  const LedgerApp({super.key});

  /// 主题种子色，改这里就能换全局主色
  static const Color kSeedColor = Color(0xFF007AFF);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '记账本',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: kSeedColor,
        brightness: Brightness.light,
      ),
      // 中文界面：让 showDatePicker / 系统组件文案都是中文。
      // TODO: 如果你的 Flutter 版本对 flutter_localizations 版本敏感，
      //       删掉下面 3 个 delegate + locale 也能跑（日期选择器会变英文）。
      locale: const Locale('zh', 'CN'),
      supportedLocales: const <Locale>[
        Locale('zh', 'CN'),
        Locale('en', 'US'),
      ],
      localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: const HomePage(),
    );
  }
}
''',
    # ----------------------------------------------------------------------
    'lib/models/record.dart': r'''// lib/models/record.dart
//
// 数据模型：一条账目 Record + 两个枚举。
// 这个文件保持"纯 Dart"（不 import flutter），方便以后写单元测试。
// 颜色以 int 形式导出，页面里用 const Color(kExpenseColorValue) 使用。

/// 全局配色常量（ARGB int）
/// TODO: 如果想换成「支出绿、收入红」的股市习惯，把这两个值对调即可。
const int kExpenseColorValue = 0xFFE53935; // 红
const int kIncomeColorValue = 0xFF2E7D32; // 绿

/// 账目类型：支出 / 收入
enum RecordType {
  expense('expense', '支出'),
  income('income', '收入');

  const RecordType(this.code, this.label);

  /// 存进 JSON 的字符串
  final String code;

  /// 界面展示的中文
  final String label;

  static RecordType fromCode(Object? code) {
    for (final t in RecordType.values) {
      if (t.code == code) return t;
    }
    return RecordType.expense;
  }
}

/// 账目来源：手动录入 / 通知自动识别
enum RecordSource {
  manual('manual', '手动'),
  auto('auto', '自动');

  const RecordSource(this.code, this.label);

  final String code;
  final String label;

  static RecordSource fromCode(Object? code) {
    for (final s in RecordSource.values) {
      if (s.code == code) return s;
    }
    return RecordSource.manual;
  }
}

/// 生成一个足够唯一的 id（单机使用，毫秒时间戳 + 微秒补位即可）
String generateRecordId() {
  final now = DateTime.now();
  return '${now.microsecondsSinceEpoch}';
}

String _two(int v) => v.toString().padLeft(2, '0');

/// 账目
class Record {
  const Record({
    required this.id,
    required this.type,
    required this.amount,
    required this.category,
    required this.date,
    this.note = '',
    this.source = RecordSource.manual,
    this.pending = false,
  });

  /// 唯一 id，用于列表 key / 编辑定位
  final String id;

  /// 支出 or 收入
  final RecordType type;

  /// 金额，恒为正数（正负由 type 决定）
  final double amount;

  /// 分类，如"餐饮"；自动记账时用商户名兜底
  final String category;

  /// 记账日期（含时分）
  final DateTime date;

  /// 备注
  final String note;

  /// 来源：手动 / 自动
  final RecordSource source;

  /// 是否待确认（自动记账进来先 pending = true，用户核对后置 false）
  final bool pending;

  /// 界面上的金额文本，带正负号
  String get amountText =>
      '${type == RecordType.expense ? '-' : '+'}${amount.toStringAsFixed(2)}';

  /// yyyy-MM-dd
  String get dateText => '${date.year}-${_two(date.month)}-${_two(date.day)}';

  /// yyyy-MM-dd HH:mm
  String get dateTimeText =>
      '$dateText ${_two(date.hour)}:${_two(date.minute)}';

  Record copyWith({
    String? id,
    RecordType? type,
    double? amount,
    String? category,
    DateTime? date,
    String? note,
    RecordSource? source,
    bool? pending,
  }) {
    return Record(
      id: id ?? this.id,
      type: type ?? this.type,
      amount: amount ?? this.amount,
      category: category ?? this.category,
      date: date ?? this.date,
      note: note ?? this.note,
      source: source ?? this.source,
      pending: pending ?? this.pending,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'id': id,
      'type': type.code,
      'amount': amount,
      'category': category,
      'date': date.toIso8601String(),
      'note': note,
      'source': source.code,
      'pending': pending,
    };
  }

  /// 容错解析：任何字段类型不对都不抛异常，退化成默认值。
  factory Record.fromJson(Map<String, dynamic> json) {
    // amount: 兼容 double / int / 字符串
    final rawAmount = json['amount'];
    double amount = 0;
    if (rawAmount is num) {
      amount = rawAmount.toDouble();
    } else if (rawAmount is String) {
      amount = double.tryParse(rawAmount.trim()) ?? 0;
    }
    if (amount.isNaN || amount.isInfinite || amount < 0) amount = 0;

    // date: 兼容 ISO 字符串 / 毫秒时间戳
    final rawDate = json['date'];
    DateTime date;
    if (rawDate is String) {
      date = DateTime.tryParse(rawDate)?.toLocal() ?? DateTime.now();
    } else if (rawDate is int) {
      date = DateTime.fromMillisecondsSinceEpoch(rawDate);
    } else if (rawDate is double) {
      date = DateTime.fromMillisecondsSinceEpoch(rawDate.toInt());
    } else {
      date = DateTime.now();
    }

    final rawCategory = json['category'];
    final category = (rawCategory is String && rawCategory.trim().isNotEmpty)
        ? rawCategory.trim()
        : '其他';

    final rawNote = json['note'];
    final rawId = json['id'];

    return Record(
      id: (rawId is String && rawId.isNotEmpty) ? rawId : generateRecordId(),
      type: RecordType.fromCode(json['type']),
      amount: amount,
      category: category,
      date: date,
      note: rawNote is String ? rawNote : '',
      source: RecordSource.fromCode(json['source']),
      pending: json['pending'] == true,
    );
  }

  @override
  String toString() =>
      'Record(id: $id, type: ${type.code}, amount: $amount, category: $category, '
      'date: ${date.toIso8601String()}, source: ${source.code}, pending: $pending)';
}
''',
    # ----------------------------------------------------------------------
    'lib/services/storage.dart': r'''// lib/services/storage.dart
//
// 持久化层：shared_preferences 里存一段 JSON 数组字符串。
// 约定：任何读取失败都返回空列表，绝不把异常抛给界面。

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/record.dart';

class Storage {
  /// 账目数据键
  static const String _recordsKey = 'records_v2';

  /// 通知权限引导弹窗是否已展示过（避免每次冷启动都弹）
  static const String _notifyGuideShownKey = 'notify_guide_shown_v1';

  // ---------------------------------------------------------------------------
  // 账目
  // ---------------------------------------------------------------------------

  /// 读取全部账目。失败（键不存在 / JSON 坏了 / 单条数据脏）一律容错。
  Future<List<Record>> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_recordsKey);
      if (raw == null || raw.isEmpty) return <Record>[];

      final decoded = jsonDecode(raw);
      if (decoded is! List) return <Record>[];

      final result = <Record>[];
      for (final item in decoded) {
        if (item is Map) {
          try {
            result.add(Record.fromJson(Map<String, dynamic>.from(item)));
          } catch (e) {
            // 单条坏了就跳过，不影响其它数据
            debugPrint('Storage.load 跳过一条脏数据: $e');
          }
        }
      }
      return result;
    } catch (e) {
      debugPrint('Storage.load 读取失败，返回空列表: $e');
      return <Record>[];
    }
  }

  /// 全量覆盖保存
  Future<void> save(List<Record> records) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final payload = jsonEncode(records.map((r) => r.toJson()).toList());
      await prefs.setString(_recordsKey, payload);
    } catch (e) {
      // 保存失败不崩溃，只打日志（比如磁盘满）
      debugPrint('Storage.save 保存失败: $e');
    }
  }

  // ---------------------------------------------------------------------------
  // 通知权限引导弹窗标记
  // ---------------------------------------------------------------------------

  Future<bool> hasShownNotifyGuide() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getBool(_notifyGuideShownKey) ?? false;
    } catch (_) {
      return false;
    }
  }

  Future<void> markNotifyGuideShown() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_notifyGuideShownKey, true);
    } catch (_) {
      // ignore
    }
  }

  /// 调试用：清空所有账目（暂时没在界面上暴露）
  Future<void> clear() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_recordsKey);
    } catch (_) {
      // ignore
    }
  }
}
''',
    # ----------------------------------------------------------------------
    'lib/services/payment_listener.dart': r'''// lib/services/payment_listener.dart
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
''',
    # ----------------------------------------------------------------------
    'lib/services/payment_parser.dart': r'''// lib/services/payment_parser.dart
//
// 通知文本解析：从微信 / 支付宝的支付通知里抽 类型 / 金额 / 商户。
//
// ⚠️ 重要：微信和支付宝的通知文案会随版本、灰度、机型变化（尤其是折叠通知和
// 服务号模板消息）。下面的关键词和正则基于常见格式，**上线前必须用真机 Logcat
// 抓到的实际文案回来调整正则**（Logcat tag = PayNotif，看 raw= 那一行）。
//
// 原则：宁可不入账，也不瞎猜。任何一步判断不出来就返回 null。

import '../models/record.dart';

/// 解析结果
class ParsedPayment {
  const ParsedPayment({
    required this.type,
    required this.amount,
    required this.merchant,
  });

  final RecordType type;
  final double amount;
  final String merchant;

  Map<String, dynamic> toMap() => <String, dynamic>{
        'type': type.code,
        'amount': amount,
        'merchant': merchant,
      };

  @override
  String toString() =>
      'ParsedPayment(type: ${type.code}, amount: $amount, merchant: $merchant)';
}

class PaymentParser {
  PaymentParser._();

  // ---------------------------------------------------------------------------
  // 关键词（TODO: 按你抓到的真实文案增删）
  // ---------------------------------------------------------------------------

  /// 收入信号
  static const List<String> _incomeKeywords = <String>[
    '到账',
    '收款',
    '入账',
    '退款',
    '收到',
    '已退还',
    '收入',
  ];

  /// 支出信号
  static const List<String> _expenseKeywords = <String>[
    '付款',
    '支付成功',
    '已支付',
    '消费',
    '扣款',
    '支出',
    '转出',
    '转账成功',
  ];

  // ---------------------------------------------------------------------------
  // 金额正则
  // 支持：¥0.01 / ￥12.3 / RMB 8 / 人民币 100 / 0.01元
  // 最多两位小数，整数最多 9 位（够用了，避免把长数字串误当金额）
  // ---------------------------------------------------------------------------

  static final RegExp _amountWithPrefix = RegExp(
    r'(?:¥|￥|RMB|人民币)\s*([0-9]{1,9}(?:\.[0-9]{1,2})?)',
    caseSensitive: false,
  );

  static final RegExp _amountWithSuffix = RegExp(
    r'([0-9]{1,9}(?:\.[0-9]{1,2})?)\s*元',
  );

  // ---------------------------------------------------------------------------
  // 商户正则（保守兜底：全失败就用"微信支付"/"支付宝"）
  // ---------------------------------------------------------------------------

  static final List<RegExp> _merchantPatterns = <RegExp>[
    // 收款方：星巴克
    RegExp(r'收款方[：:]\s*([^\s，,。;；:：、]{1,24})'),
    // 商户：星巴克
    RegExp(r'商户[：:]\s*([^\s，,。;；:：、]{1,24})'),
    // 向星巴克付款 / 付款给星巴克 / 转账给张三
    RegExp(r'(?:向|付款给|转账给|转给)([^\s，,。;；:：、]{1,24}?)(?:付款|转账|支付|成功|，|,|。|$|】)'),
    // 在星巴克消费
    RegExp(r'在([^\s，,。;；:：、]{1,24}?)(?:消费|付款|支付|的)'),
    // 【星巴克】你已支付 0.01 元
    RegExp(r'【([^】]{1,24})】'),
  ];

  /// 明显不是商户的噪声词（命中就认为提取失败）
  static const List<String> _noiseWords = <String>[
    '微信支付',
    '微信',
    '支付宝',
    'Alipay',
    '支付成功',
    '付款成功',
    '交易提醒',
    '通知',
    '零钱',
    '余额宝',
    '花呗',
    '银行卡',
    '你',
  ];

  /// 纯数字/纯金额形态：如 "0.01"、"12元"
  static final RegExp _pureNumber = RegExp(r'^[0-9]+(?:\.[0-9]+)?\s*元?$');

  // ---------------------------------------------------------------------------
  // 主入口
  // ---------------------------------------------------------------------------

  /// 解析一条通知。
  /// [source] 'wechat' / 'alipay'
  /// 返回 null 表示"无法判断，不处理"。
  static ParsedPayment? parse({
    required String source,
    String title = '',
    String text = '',
    String bigText = '',
  }) {
    // 拼接语料：标题通常含"微信支付/支付宝"，正文含金额，大文本是正文的展开
    final corpus = <String>[title, text, bigText]
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .join('  ');
    if (corpus.isEmpty) return null;

    final type = _detectType(corpus);
    if (type == null) return null; // 分不清收还是支，直接放弃

    final amount = _detectAmount(corpus);
    if (amount == null || amount <= 0) return null; // 没有可信金额，放弃

    final merchant = _detectMerchant(corpus) ??
        (source == 'wechat' ? '微信支付' : '支付宝');

    return ParsedPayment(
      type: type,
      amount: double.parse(amount.toStringAsFixed(2)),
      merchant: merchant,
    );
  }

  // ---------------------------------------------------------------------------
  // 内部实现
  // ---------------------------------------------------------------------------

  static RecordType? _detectType(String corpus) {
    final hasIncome = _incomeKeywords.any(corpus.contains);
    final hasExpense = _expenseKeywords.any(corpus.contains);

    // 两个方向同时命中（例如"退款"+"付款"混在一段里）→ 不猜
    if (hasIncome && hasExpense) return null;
    if (hasIncome) return RecordType.income;
    if (hasExpense) return RecordType.expense;
    return null;
  }

  static double? _detectAmount(String corpus) {
    // 先找带货币符号的（最可靠）
    final withPrefix = _amountWithPrefix.firstMatch(corpus);
    if (withPrefix != null) {
      return double.tryParse(withPrefix.group(1) ?? '');
    }
    // 再找 "0.01元" 这种后缀形式
    final withSuffix = _amountWithSuffix.firstMatch(corpus);
    if (withSuffix != null) {
      return double.tryParse(withSuffix.group(1) ?? '');
    }
    // 没有单位的一律不认（"余额100元"这种也被前缀/后缀兜住了，剩余情况不猜）
    return null;
  }

  static String? _detectMerchant(String corpus) {
    for (final pattern in _merchantPatterns) {
      final match = pattern.firstMatch(corpus);
      if (match == null) continue;
      final candidate = _cleanMerchant(match.group(1));
      if (candidate != null) return candidate;
    }
    return null;
  }

  static String? _cleanMerchant(String? raw) {
    if (raw == null) return null;
    var value = raw.trim();
    // 去掉首尾标点和空白
    value = value.replaceAll(RegExp(r'^[\s，,。.;；:：、\-—]+'), '');
    value = value.replaceAll(RegExp(r'[\s，,。.;；:：、\-—]+$'), '');
    if (value.length < 2) return null;
    if (_pureNumber.hasMatch(value)) return null;
    if (_noiseWords.contains(value)) return null;
    // 太长基本是整句被吞了，不采信
    if (value.length > 24) return null;
    return value;
  }
}
''',
    # ----------------------------------------------------------------------
    'lib/screens/home_page.dart': r'''// lib/screens/home_page.dart
//
// 首页：汇总卡片 + 账目列表 + 手动记账入口 + 待确认入口 + 自动记账订阅。

import 'dart:async';

import 'package:flutter/material.dart';

import '../models/record.dart';
import '../services/payment_listener.dart';
import '../services/payment_parser.dart';
import '../services/storage.dart';
import 'add_page.dart';
import 'pending_page.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with WidgetsBindingObserver {
  final Storage _storage = Storage();

  /// 全部账目（内存里的唯一数据源）
  final List<Record> _records = <Record>[];

  /// 自动记账去重 key 缓存：source|金额|30秒时间桶（最多 100 条）
  final Set<String> _dedupKeys = <String>{};
  static const int _dedupLimit = 100;

  StreamSubscription<PaymentEvent>? _paymentSub;

  bool _loading = true;
  bool _notifyGranted = true;

  // ---------------------------------------------------------------------------
  // 生命周期
  // ---------------------------------------------------------------------------

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _bootstrap();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _paymentSub?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // 从系统设置页切回来时，重新检查一遍通知使用权
    if (state == AppLifecycleState.resumed) {
      _refreshNotifyPermission();
    }
  }

  Future<void> _bootstrap() async {
    final loaded = await _storage.load();
    if (!mounted) return;

    _records
      ..clear()
      ..addAll(loaded);
    _sortRecords();
    setState(() => _loading = false);

    _subscribePayments();
    await _checkNotifyPermission(allowPrompt: true);
  }

  // ---------------------------------------------------------------------------
  // 通知权限
  // ---------------------------------------------------------------------------

  Future<void> _refreshNotifyPermission() async {
    final granted = await PaymentListener.hasPermission();
    if (!mounted) return;
    if (granted != _notifyGranted) {
      setState(() => _notifyGranted = granted);
    }
  }

  Future<void> _checkNotifyPermission({required bool allowPrompt}) async {
    final granted = await PaymentListener.hasPermission();
    if (!mounted) return;
    setState(() => _notifyGranted = granted);

    if (granted || !allowPrompt) return;

    // 只在首次启动引导一次，之后靠 AppBar 上的小铃铛入口
    final shown = await _storage.hasShownNotifyGuide();
    if (!mounted || shown) return;
    await _storage.markNotifyGuideShown();
    if (!mounted) return;
    await _showNotifyGuideDialog();
  }

  Future<void> _showNotifyGuideDialog() async {
    final go = await showDialog<bool>(
      context: context,
      builder: (BuildContext ctx) {
        return AlertDialog(
          title: const Text('开启自动记账'),
          content: const Text(
            '记账本需要「通知使用权」，才能读取微信 / 支付宝的支付通知，'
            '自动生成待确认账目。\n\n'
            '点「去开启」后，在系统列表里找到「记账本」并打开开关即可。'
            '不开也能正常手动记账。',
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('稍后'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('去开启'),
            ),
          ],
        );
      },
    );
    if (go == true) {
      await PaymentListener.openSettings();
    }
  }

  // ---------------------------------------------------------------------------
  // 数据工具
  // ---------------------------------------------------------------------------

  void _sortRecords() {
    _records.sort((Record a, Record b) {
      final int byDate = b.date.compareTo(a.date);
      if (byDate != 0) return byDate;
      // 同一时间戳的，后插入的排前面（id 是微秒时间戳，可以比较长度后字典序）
      return b.id.compareTo(a.id);
    });
  }

  Future<void> _persist() => _storage.save(_records);

  double get _totalIncome => _records
      .where((Record r) => !r.pending && r.type == RecordType.income)
      .fold<double>(0, (double sum, Record r) => sum + r.amount);

  double get _totalExpense => _records
      .where((Record r) => !r.pending && r.type == RecordType.expense)
      .fold<double>(0, (double sum, Record r) => sum + r.amount);

  double get _balance => _totalIncome - _totalExpense;

  int get _pendingCount => _records.where((Record r) => r.pending).length;

  // ---------------------------------------------------------------------------
  // 手动记账 / 编辑
  // ---------------------------------------------------------------------------

  Future<void> _openAddPage({Record? initial}) async {
    final Record? result = await Navigator.of(context).push<Record>(
      MaterialPageRoute<Record>(builder: (_) => AddPage(initial: initial)),
    );
    if (result == null || !mounted) return;

    setState(() {
      final int index = _records.indexWhere((Record r) => r.id == result.id);
      if (index >= 0) {
        _records[index] = result;
      } else {
        _records.add(result);
      }
      _sortRecords();
    });
    await _persist();
  }

  Future<void> _deleteRecord(Record record) async {
    final int index = _records.indexWhere((Record r) => r.id == record.id);
    if (index < 0) return;

    setState(() => _records.removeAt(index));
    await _persist();
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('已删除「${record.category}」¥${record.amount.toStringAsFixed(2)}'),
        action: SnackBarAction(
          label: '撤销',
          onPressed: () async {
            if (!mounted) return;
            setState(() {
              _records.add(record);
              _sortRecords();
            });
            await _persist();
          },
        ),
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // 待确认页
  // ---------------------------------------------------------------------------

  Future<void> _openPendingPage() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => PendingPage(
          records: List<Record>.of(_records),
          onChanged: (List<Record> updated) async {
            if (!mounted) return;
            setState(() {
              _records
                ..clear()
                ..addAll(updated);
              _sortRecords();
            });
            await _persist();
          },
        ),
      ),
    );
    // 回到首页再兜底刷一次权限状态
    await _refreshNotifyPermission();
  }

  // ---------------------------------------------------------------------------
  // 自动记账：订阅通知事件
  // ---------------------------------------------------------------------------

  void _subscribePayments() {
    _paymentSub?.cancel();
    _paymentSub = PaymentListener.stream().listen(
      _onPaymentEvent,
      onError: (Object error) {
        debugPrint('自动记账流异常: $error');
      },
    );
  }

  Future<void> _onPaymentEvent(PaymentEvent event) async {
    final ParsedPayment? parsed = PaymentParser.parse(
      source: event.source,
      title: event.title,
      text: event.text,
      bigText: event.bigText,
    );

    if (parsed == null) {
      // 解析不出来就只留日志，不入账（宁缺勿滥）
      debugPrint('[自动记账] 忽略无法识别的通知: ${event.raw}');
      return;
    }

    // 去重：同一笔支付通知常常会被系统重复 post，用 30 秒时间桶 + 金额 + 渠道
    final int bucket = event.timestamp ~/ 30000;
    final String dedupKey =
        '${event.source}|${parsed.amount.toStringAsFixed(2)}|$bucket';
    if (_dedupKeys.contains(dedupKey)) {
      debugPrint('[自动记账] 命中去重，跳过: $dedupKey');
      return;
    }
    _dedupKeys.add(dedupKey);
    if (_dedupKeys.length > _dedupLimit) {
      // 只保留最近 100 个（Set 迭代顺序 = 插入顺序）
      _dedupKeys.remove(_dedupKeys.first);
    }

    final Record record = Record(
      id: generateRecordId(),
      type: parsed.type,
      amount: parsed.amount,
      // 自动记账不猜分类，直接用商户名当分类，用户可在编辑里改
      category: parsed.merchant,
      date: DateTime.now(),
      note: '${event.sourceLabel}支付通知自动识别，待确认',
      source: RecordSource.auto,
      pending: true,
    );

    setState(() {
      _records.insert(0, record);
      _sortRecords();
    });
    await _persist();

    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          '自动记账：${record.type.label} ¥${record.amount.toStringAsFixed(2)}（待确认）',
        ),
        action: SnackBarAction(
          label: '去确认',
          onPressed: _openPendingPage,
        ),
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // UI
  // ---------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('记账本'),
        actions: <Widget>[
          if (!_notifyGranted)
            IconButton(
              tooltip: '未开启通知使用权，点击去设置',
              icon: const Icon(Icons.notifications_off_outlined),
              onPressed: () async {
                await PaymentListener.openSettings();
              },
            ),
          IconButton(
            tooltip: '待确认',
            onPressed: _openPendingPage,
            icon: Badge.count(
              count: _pendingCount,
              isLabelVisible: _pendingCount > 0,
              child: const Icon(Icons.playlist_add_check_outlined),
            ),
          ),
          const SizedBox(width: 4),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _openAddPage(),
        icon: const Icon(Icons.add),
        label: const Text('记一笔'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: <Widget>[
                _buildSummaryCard(theme),
                Expanded(child: _buildRecordList(theme)),
              ],
            ),
    );
  }

  Widget _buildSummaryCard(ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: Card(
        margin: EdgeInsets.zero,
        elevation: 0,
        color: theme.colorScheme.surfaceVariant.withOpacity(0.5),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 8),
          child: Column(
            children: <Widget>[
              Row(
                children: <Widget>[
                  _summaryItem(
                    theme,
                    label: '收入',
                    value: _totalIncome,
                    color: const Color(kIncomeColorValue),
                  ),
                  _summaryDivider(theme),
                  _summaryItem(
                    theme,
                    label: '支出',
                    value: _totalExpense,
                    color: const Color(kExpenseColorValue),
                  ),
                  _summaryDivider(theme),
                  _summaryItem(
                    theme,
                    label: '结余',
                    value: _balance,
                    color: theme.colorScheme.onSurface,
                  ),
                ],
              ),
              if (_pendingCount > 0) ...<Widget>[
                const SizedBox(height: 10),
                Text(
                  '另有 $_pendingCount 笔待确认，未计入上方合计',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _summaryDivider(ThemeData theme) {
    return Container(
      width: 1,
      height: 34,
      color: theme.colorScheme.outlineVariant,
    );
  }

  Widget _summaryItem(
    ThemeData theme, {
    required String label,
    required double value,
    required Color color,
  }) {
    return Expanded(
      child: Column(
        children: <Widget>[
          Text(
            label,
            style: theme.textTheme.labelMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 6),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              '¥${value.toStringAsFixed(2)}',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
                color: color,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecordList(ThemeData theme) {
    if (_records.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              Icons.receipt_long_outlined,
              size: 56,
              color: theme.colorScheme.outline,
            ),
            const SizedBox(height: 12),
            Text(
              '还没有账目，点右下角记第一笔',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.outline,
              ),
            ),
          ],
        ),
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.only(bottom: 96),
      itemCount: _records.length,
      separatorBuilder: (BuildContext context, int index) =>
          const Divider(height: 1, indent: 72),
      itemBuilder: (BuildContext context, int index) =>
          _buildRecordTile(theme, _records[index]),
    );
  }

  Widget _buildRecordTile(ThemeData theme, Record record) {
    final bool isExpense = record.type == RecordType.expense;
    final Color amountColor = Color(
      isExpense ? kExpenseColorValue : kIncomeColorValue,
    );

    final List<String> subtitleParts = <String>[record.dateTimeText];
    if (record.note.isNotEmpty) subtitleParts.add(record.note);

    return Dismissible(
      key: ValueKey<String>(record.id),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        color: theme.colorScheme.errorContainer,
        child: Icon(
          Icons.delete_outline,
          color: theme.colorScheme.onErrorContainer,
        ),
      ),
      onDismissed: (DismissDirection direction) {
        _deleteRecord(record);
      },
      child: ListTile(
        onTap: () => _openAddPage(initial: record),
        leading: CircleAvatar(
          backgroundColor: amountColor.withOpacity(0.12),
          child: Icon(
            isExpense ? Icons.arrow_upward : Icons.arrow_downward,
            color: amountColor,
            size: 20,
          ),
        ),
        title: Row(
          children: <Widget>[
            Flexible(
              child: Text(
                record.category,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodyLarge,
              ),
            ),
            if (record.source == RecordSource.auto) ...<Widget>[
              const SizedBox(width: 6),
              _sourceTag(theme),
            ],
            if (record.pending) ...<Widget>[
              const SizedBox(width: 6),
              _pendingTag(),
            ],
          ],
        ),
        subtitle: Text(
          subtitleParts.join(' · '),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        trailing: Text(
          record.amountText,
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: amountColor,
          ),
        ),
      ),
    );
  }

  /// 黄色"待确认"小标签
  Widget _pendingTag() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF3C4),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: const Color(0xFFFFE082)),
      ),
      child: const Text(
        '待确认',
        style: TextStyle(
          fontSize: 10,
          height: 1.4,
          color: Color(0xFF8A6D00),
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  /// 灰色"自动"小标签
  Widget _sourceTag(ThemeData theme) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        color: theme.colorScheme.secondaryContainer,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        '自动',
        style: TextStyle(
          fontSize: 10,
          height: 1.4,
          color: theme.colorScheme.onSecondaryContainer,
        ),
      ),
    );
  }
}
''',
    # ----------------------------------------------------------------------
    'lib/screens/add_page.dart': r'''// lib/screens/add_page.dart
//
// 手动记账 / 编辑账目页。
// 保存时 Navigator.pop 返回一个 Record：
//  - 新增：id 新生成，source = manual，pending = false
//  - 编辑：沿用原 id / source / pending（保证待确认记录编辑后仍在待确认列表里）

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/record.dart';

class AddPage extends StatefulWidget {
  /// null = 新增；非 null = 编辑该条记录
  final Record? initial;

  const AddPage({super.key, this.initial});

  @override
  State<AddPage> createState() => _AddPageState();
}

class _AddPageState extends State<AddPage> {
  // TODO: 分类写死在这里，想改成用户自定义分类可以以后接一层 prefs 存储
  static const List<String> _expenseCategories = <String>[
    '餐饮',
    '交通',
    '购物',
    '居住',
    '娱乐',
    '医疗',
    '其他',
  ];

  static const List<String> _incomeCategories = <String>[
    '工资',
    '奖金',
    '理财',
    '红包',
    '其他',
  ];

  final TextEditingController _amountCtrl = TextEditingController();
  final TextEditingController _categoryCtrl = TextEditingController();
  final TextEditingController _noteCtrl = TextEditingController();

  late RecordType _type;
  late DateTime _date;

  bool get _isEditing => widget.initial != null;

  List<String> get _categories =>
      _type == RecordType.expense ? _expenseCategories : _incomeCategories;

  Color get _typeColor => Color(
        _type == RecordType.expense ? kExpenseColorValue : kIncomeColorValue,
      );

  @override
  void initState() {
    super.initState();
    final init = widget.initial;
    _type = init?.type ?? RecordType.expense;
    _date = init?.date ?? DateTime.now();

    if (init != null) {
      _amountCtrl.text = init.amount == 0 ? '' : init.amount.toStringAsFixed(2);
      _categoryCtrl.text = init.category;
      _noteCtrl.text = init.note;
    }

    // 分类输入框内容变化时刷新快捷 Chip 的选中态
    _categoryCtrl.addListener(_onTextChanged);
  }

  @override
  void dispose() {
    _categoryCtrl.removeListener(_onTextChanged);
    _amountCtrl.dispose();
    _categoryCtrl.dispose();
    _noteCtrl.dispose();
    super.dispose();
  }

  void _onTextChanged() {
    if (mounted) setState(() {});
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _date.isAfter(DateTime(now.year + 1, 12, 31))
          ? now
          : _date,
      firstDate: DateTime(now.year - 10),
      lastDate: DateTime(now.year + 1, 12, 31),
      helpText: '选择账目日期',
      cancelText: '取消',
      confirmText: '确定',
    );
    if (picked == null) return;
    setState(() {
      // 只替换年月日，时分沿用原来的（保持排序稳定）
      _date = DateTime(
        picked.year,
        picked.month,
        picked.day,
        _date.hour,
        _date.minute,
      );
    });
  }

  void _save() {
    final text = _amountCtrl.text.trim();
    if (text.isEmpty) {
      _showError('请输入金额');
      return;
    }
    if (!RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(text)) {
      _showError('金额格式不对，最多两位小数');
      return;
    }
    final amount = double.tryParse(text);
    if (amount == null || amount <= 0) {
      _showError('金额必须大于 0');
      return;
    }

    final categoryText = _categoryCtrl.text.trim();
    final record = Record(
      id: widget.initial?.id ?? generateRecordId(),
      type: _type,
      amount: double.parse(amount.toStringAsFixed(2)),
      category: categoryText.isEmpty ? '其他' : categoryText,
      date: _date,
      note: _noteCtrl.text.trim(),
      source: widget.initial?.source ?? RecordSource.manual,
      pending: widget.initial?.pending ?? false,
    );

    Navigator.of(context).pop(record);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final selectedCategory = _categoryCtrl.text.trim();

    return Scaffold(
      appBar: AppBar(
        title: Text(_isEditing ? '编辑账目' : '记一笔'),
        actions: <Widget>[
          TextButton(
            onPressed: _save,
            child: const Text('保存'),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
        children: <Widget>[
          // ---------------- 支出 / 收入 ----------------
          Center(
            child: SegmentedButton<RecordType>(
              segments: const <ButtonSegment<RecordType>>[
                ButtonSegment<RecordType>(
                  value: RecordType.expense,
                  label: Text('支出'),
                  icon: Icon(Icons.arrow_upward),
                ),
                ButtonSegment<RecordType>(
                  value: RecordType.income,
                  label: Text('收入'),
                  icon: Icon(Icons.arrow_downward),
                ),
              ],
              selected: <RecordType>{_type},
              onSelectionChanged: (Set<RecordType> selection) {
                setState(() => _type = selection.first);
              },
            ),
          ),
          const SizedBox(height: 24),

          // ---------------- 金额 ----------------
          TextField(
            controller: _amountCtrl,
            autofocus: !_isEditing,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: <TextInputFormatter>[
              // 只允许数字和小数点；多位小数由 _save 里的正则再校验一次
              FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
            ],
            style: theme.textTheme.headlineMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: _typeColor,
            ),
            decoration: const InputDecoration(
              labelText: '金额',
              prefixText: '¥ ',
              hintText: '0.00',
              border: OutlineInputBorder(),
              helperText: '只填数字，最多两位小数',
            ),
          ),
          const SizedBox(height: 20),

          // ---------------- 分类 ----------------
          TextField(
            controller: _categoryCtrl,
            textInputAction: TextInputAction.next,
            decoration: const InputDecoration(
              labelText: '分类',
              hintText: '例如：餐饮',
              border: OutlineInputBorder(),
              helperText: '可手动输入，也可点下面的快捷标签',
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _categories.map((String category) {
              return ChoiceChip(
                label: Text(category),
                selected: selectedCategory == category,
                onSelected: (bool selected) {
                  // 选中就填入，再点一次清空
                  _categoryCtrl.text = selected ? category : '';
                  _categoryCtrl.selection = TextSelection.collapsed(
                    offset: _categoryCtrl.text.length,
                  );
                },
              );
            }).toList(),
          ),
          const SizedBox(height: 20),

          // ---------------- 日期 ----------------
          Card(
            margin: EdgeInsets.zero,
            child: ListTile(
              leading: const Icon(Icons.event_outlined),
              title: const Text('日期'),
              subtitle: Text('${_date.year}-${_date.month.toString().padLeft(2, '0')}-'
                  '${_date.day.toString().padLeft(2, '0')}'),
              trailing: const Icon(Icons.chevron_right),
              onTap: _pickDate,
            ),
          ),
          const SizedBox(height: 20),

          // ---------------- 备注 ----------------
          TextField(
            controller: _noteCtrl,
            maxLines: 3,
            minLines: 1,
            textInputAction: TextInputAction.done,
            decoration: const InputDecoration(
              labelText: '备注',
              hintText: '写点什么（可不填）',
              border: OutlineInputBorder(),
              alignLabelWithHint: true,
            ),
          ),
          const SizedBox(height: 28),

          // ---------------- 保存 ----------------
          SizedBox(
            height: 50,
            child: FilledButton.icon(
              onPressed: _save,
              icon: const Icon(Icons.check),
              label: Text(_isEditing ? '保存修改' : '保存'),
            ),
          ),
        ],
      ),
    );
  }
}
''',
    # ----------------------------------------------------------------------
    'lib/screens/pending_page.dart': r'''// lib/screens/pending_page.dart
//
// 待确认页：列出所有 pending == true 的账目，可单条确认 / 删除，也可全部确认。
// 每次改动都通过 onChanged 回传给 HomePage 并立即持久化。

import 'package:flutter/material.dart';

import '../models/record.dart';

class PendingPage extends StatefulWidget {
  const PendingPage({
    super.key,
    required this.records,
    required this.onChanged,
  });

  /// 传入完整列表（内部只显示 pending 的）
  final List<Record> records;

  /// 任意变更后回传完整列表，由 HomePage 负责 setState + 存盘
  final ValueChanged<List<Record>> onChanged;

  @override
  State<PendingPage> createState() => _PendingPageState();
}

class _PendingPageState extends State<PendingPage> {
  late List<Record> _records;

  @override
  void initState() {
    super.initState();
    _records = List<Record>.of(widget.records);
  }

  List<Record> get _pendingList {
    final List<Record> list =
        _records.where((Record r) => r.pending).toList();
    list.sort((Record a, Record b) => b.date.compareTo(a.date));
    return list;
  }

  void _notify() {
    widget.onChanged(List<Record>.of(_records));
  }

  void _confirmOne(Record record) {
    setState(() {
      final int index = _records.indexWhere((Record r) => r.id == record.id);
      if (index >= 0) {
        _records[index] = _records[index].copyWith(pending: false);
      }
    });
    _notify();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('已入账：${record.category} ¥${record.amount.toStringAsFixed(2)}'),
        duration: const Duration(milliseconds: 1200),
      ),
    );
  }

  void _deleteOne(Record record) {
    setState(() {
      _records.removeWhere((Record r) => r.id == record.id);
    });
    _notify();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('已删除：${record.category} ¥${record.amount.toStringAsFixed(2)}'),
        duration: const Duration(milliseconds: 1200),
      ),
    );
  }

  void _confirmAll() {
    final int count = _pendingList.length;
    if (count == 0) return;

    setState(() {
      for (int i = 0; i < _records.length; i++) {
        if (_records[i].pending) {
          _records[i] = _records[i].copyWith(pending: false);
        }
      }
    });
    _notify();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('已全部确认 $count 笔'),
        duration: const Duration(milliseconds: 1200),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<Record> list = _pendingList;

    return Scaffold(
      appBar: AppBar(
        title: Text('待确认${list.isEmpty ? '' : '（${list.length}）'}'),
        actions: <Widget>[
          TextButton(
            onPressed: list.isEmpty ? null : _confirmAll,
            child: const Text('全部确认'),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: list.isEmpty
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Icon(
                    Icons.check_circle_outline,
                    size: 56,
                    color: theme.colorScheme.outline,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    '没有待确认的账目',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.outline,
                    ),
                  ),
                ],
              ),
            )
          : ListView.separated(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 32),
              itemCount: list.length,
              separatorBuilder: (BuildContext context, int index) =>
                  const SizedBox(height: 10),
              itemBuilder: (BuildContext context, int index) {
                final Record record = list[index];
                return _buildCard(theme, record);
              },
            ),
    );
  }

  Widget _buildCard(ThemeData theme, Record record) {
    final bool isExpense = record.type == RecordType.expense;
    final Color amountColor = Color(
      isExpense ? kExpenseColorValue : kIncomeColorValue,
    );

    return Card(
      margin: EdgeInsets.zero,
      elevation: 0,
      color: theme.colorScheme.surfaceVariant.withOpacity(0.4),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 12, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(
                  isExpense ? Icons.arrow_upward : Icons.arrow_downward,
                  size: 18,
                  color: amountColor,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    record.category,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.titleSmall,
                  ),
                ),
                Text(
                  '${isExpense ? '-' : '+'}¥${record.amount.toStringAsFixed(2)}',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: amountColor,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              <String>[
                record.dateTimeText,
                record.type.label,
                record.note.isEmpty ? '无备注' : record.note,
              ].join(' · '),
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 4),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: <Widget>[
                TextButton.icon(
                  onPressed: () => _deleteOne(record),
                  icon: const Icon(Icons.delete_outline, size: 18),
                  label: const Text('删除'),
                  style: TextButton.styleFrom(
                    foregroundColor: theme.colorScheme.error,
                  ),
                ),
                const SizedBox(width: 4),
                FilledButton.tonalIcon(
                  onPressed: () => _confirmOne(record),
                  icon: const Icon(Icons.check, size: 18),
                  label: const Text('确认入账'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
''',
    # ----------------------------------------------------------------------
    'android/app/build.gradle': r'''// android/app/build.gradle
//
// 补充文件（题目要求的目录结构里没列，但 minSdk 21 / targetSdk 34 必须在这里改）。
// 注意：Flutter 3.29+ 的 `flutter create` 生成的是 build.gradle.kts，语法不同，
// 如果你的是 .kts 文件，把下面 android { } 里的三个值抄过去即可：
//     minSdk = 21 / targetSdk = 34 / applicationId = "com.example.ledger"

plugins {
    id "com.android.application"
    id "kotlin-android"
    id "dev.flutter.flutter-gradle-plugin"
}

android {
    namespace = "com.example.ledger"     // TODO: 改成你的包名（与 kotlin 目录一致）
    compileSdk = 34

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }

    kotlinOptions {
        jvmTarget = "1.8"
    }

    defaultConfig {
        applicationId = "com.example.ledger"   // TODO: 改成你的包名，如 com.yourname.ledger
        minSdk = 21        // TODO: 新版 Flutter（3.29+）默认 minSdk 已是 24，若构建报错改成 24
        targetSdk = 34
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // TODO: 正式发版请换成自己的签名配置，这里是 Flutter 默认的 debug 签名
            signingConfig = signingConfigs.debug
            minifyEnabled = false
            shrinkResources = false
        }
    }
}

flutter {
    source = "../.."
}
''',
    # ----------------------------------------------------------------------
    'android/app/src/main/AndroidManifest.xml': r'''<?xml version="1.0" encoding="utf-8"?>
<!-- android/app/src/main/AndroidManifest.xml -->
<!--
  说明：
  1) 这里**故意没有** <uses-permission android:name="android.permission.INTERNET"/>
     —— App 完全离线，不联网。
  2) 通知监听服务的三要素：service 节点 + BIND_NOTIFICATION_LISTENER_SERVICE 权限
     + action = android.service.notification.NotificationListenerService 的 intent-filter。
  3) 改包名时，android:name=".MainActivity" / ".PaymentNotificationService" 是相对
     包名的写法，只要 applicationId 与 kotlin 目录的 package 一致就不用改这里。
-->
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <application
        android:label="记账本"
        android:name="${applicationName}"
        android:icon="@mipmap/ic_launcher">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:launchMode="singleTop"
            android:theme="@style/LaunchTheme"
            android:configChanges="orientation|keyboardHidden|keyboard|screenSize|smallestScreenSize|locale|layoutDirection|fontScale|screenLayout|density|uiMode"
            android:hardwareAccelerated="true"
            android:windowSoftInputMode="adjustResize">
            <!-- Flutter 启动主题 -->
            <meta-data
                android:name="io.flutter.embedding.android.NormalTheme"
                android:resource="@style/NormalTheme" />
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <!-- ===================== 通知监听服务 ===================== -->
        <!--
          exported 必须为 true，因为系统（NotificationListenerService 的宿主）要能绑定它。
          权限 BIND_NOTIFICATION_LISTENER_SERVICE 保证只有系统能绑，普通 App 绑不上。
        -->
        <service
            android:name=".PaymentNotificationService"
            android:exported="true"
            android:label="记账本自动记账"
            android:permission="android.permission.BIND_NOTIFICATION_LISTENER_SERVICE">
            <intent-filter>
                <action android:name="android.service.notification.NotificationListenerService" />
            </intent-filter>
        </service>

        <!-- Flutter Embedding v2 -->
        <meta-data
            android:name="flutterEmbedding"
            android:value="2" />
    </application>

    <!-- Flutter 默认需要的 queries（文本处理），与网络无关 -->
    <queries>
        <intent>
            <action android:name="android.intent.action.PROCESS_TEXT" />
            <data android:mimeType="text/plain" />
        </intent>
    </queries>
</manifest>
''',
    # ----------------------------------------------------------------------
    'android/app/src/main/kotlin/com/example/ledger/MainActivity.kt': r'''// android/app/src/main/kotlin/com/example/ledger/MainActivity.kt
//
// Flutter 宿主 Activity：
//  1) MethodChannel "ledger/notify"
//       - hasPermission : 是否已授予"通知使用权"
//       - openSettings  : 跳转系统通知使用权设置页
//  2) EventChannel "ledger/events"：把 EventSink 交给 PaymentNotificationService，
//     由 Service 在收到微信/支付宝通知时把数据推给 Flutter。
//
// TODO: 改包名时，这里的 package 也要跟着改，并且目录要一起挪：
//       android/app/src/main/kotlin/<你的包路径>/MainActivity.kt

package com.example.ledger

import android.content.ComponentName
import android.content.Intent
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    private companion object {
        const val METHOD_CHANNEL = "ledger/notify"
        const val EVENT_CHANNEL = "ledger/events"
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val messenger = flutterEngine.dartExecutor.binaryMessenger

        // ---------------- MethodChannel ----------------
        MethodChannel(messenger, METHOD_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "hasPermission" -> {
                    result.success(isNotificationListenerEnabled())
                }

                "openSettings" -> {
                    try {
                        val intent = Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        startActivity(intent)
                        result.success(true)
                    } catch (e: Exception) {
                        // 极少数 ROM 没有这个设置页，兜底跳到应用详情
                        try {
                            val fallback = Intent(Settings.ACTION_SETTINGS)
                            fallback.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            startActivity(fallback)
                            result.success(true)
                        } catch (e2: Exception) {
                            result.error("OPEN_SETTINGS_FAILED", e2.message, null)
                        }
                    }
                }

                else -> result.notImplemented()
            }
        }

        // ---------------- EventChannel ----------------
        EventChannel(messenger, EVENT_CHANNEL).setStreamHandler(
            object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    // Flutter 侧开始监听：把 sink 交给 Service 持有
                    PaymentNotificationService.eventSink = events
                }

                override fun onCancel(arguments: Any?) {
                    PaymentNotificationService.eventSink = null
                }
            }
        )
    }

    /**
     * 判断本应用是否在"已启用的通知监听器"列表里。
     * 官方没有直接 API，标准做法是读 Settings.Secure 里的
     * enabled_notification_listeners（形如 "pkg/cls:pkg/cls"）。
     */
    private fun isNotificationListenerEnabled(): Boolean {
        val flat = Settings.Secure.getString(
            contentResolver,
            "enabled_notification_listeners"
        )
        if (flat.isNullOrEmpty()) return false

        val myPackage = applicationContext.packageName
        return flat.split(":").any { entry ->
            ComponentName.unflattenFromString(entry)?.packageName == myPackage
        }
    }
}
''',
    # ----------------------------------------------------------------------
    'android/app/src/main/kotlin/com/example/ledger/PaymentNotificationService.kt': r'''// android/app/src/main/kotlin/com/example/ledger/PaymentNotificationService.kt
//
// 通知监听服务：只关心微信（com.tencent.mm）和支付宝（com.eg.android.AlipayGphone）。
// 拿到通知后把 title / text / bigText / textLines / raw 一股脑通过 EventChannel
// 推给 Flutter，解析（金额、收支方向、商户）全部在 Dart 侧做。
//
// 调试：Logcat 过滤 tag = PayNotif，能看到每条原始文本。
//
// 注意：本 Service 只负责"捞原文"，不做任何判断，避免原生侧和 Dart 侧逻辑重复。

package com.example.ledger

import android.app.Notification
import android.os.Handler
import android.os.Looper
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import io.flutter.plugin.common.EventChannel

class PaymentNotificationService : NotificationListenerService() {

    companion object {
        private const val TAG = "PayNotif"

        /**
         * 只处理这两个包。
         * TODO: 如果以后要接其它支付渠道（如云闪付 unionpay），在这里加映射即可，
         *       同时在 Dart 侧 PaymentParser 里补关键词。
         */
        private val TARGET_PACKAGES = mapOf(
            "com.tencent.mm" to "wechat",
            "com.eg.android.AlipayGphone" to "alipay"
        )

        /**
         * Flutter 侧的 EventSink。由 MainActivity 的 EventChannel onListen 赋值。
         * 用 @Volatile 保证跨线程可见性；Service 回调在 Binder 线程，发送要切主线程。
         */
        @Volatile
        var eventSink: EventChannel.EventSink? = null

        private val mainHandler = Handler(Looper.getMainLooper())
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        Log.d(TAG, "通知监听已连接，可以开始抓微信/支付宝通知了")
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        Log.d(TAG, "通知监听已断开（可能被系统回收或用户关闭了开关）")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        val notification = sbn ?: return
        val pkg = notification.packageName ?: return

        // 1) 包名过滤：不是微信/支付宝直接返回，不产生任何开销
        val source = TARGET_PACKAGES[pkg] ?: return

        val extras = notification.notification?.extras ?: return

        // 2) 提取各字段（全部做空安全处理，取不到就是空串）
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty()
        val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty()
        val lines: List<String> = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)
            ?.map { it?.toString().orEmpty() }
            ?: emptyList()

        val raw = listOf(title, text, bigText, lines.joinToString(" / "))
            .filter { it.isNotBlank() }
            .joinToString(" | ")

        // 3) 打日志，方便用 Logcat 校准 Dart 侧正则
        Log.d(TAG, "---- 收到 $pkg ($source) ----")
        Log.d(TAG, "title   = $title")
        Log.d(TAG, "text    = $text")
        Log.d(TAG, "bigText = $bigText")
        Log.d(TAG, "lines   = $lines")
        Log.d(TAG, "raw     = $raw")

        if (raw.isBlank()) {
            Log.d(TAG, "文本为空（可能是纯图标通知），跳过")
            return
        }

        // 4) 组装 payload
        val payload = HashMap<String, Any?>()
        payload["source"] = source
        payload["packageName"] = pkg
        payload["title"] = title
        payload["text"] = text
        payload["bigText"] = bigText
        payload["lines"] = lines
        payload["raw"] = raw
        payload["timestamp"] = notification.postTime   // 毫秒时间戳
        payload["notificationId"] = notification.id

        val sink = eventSink
        if (sink == null) {
            // Flutter 引擎没起来（App 被杀 / 还没订阅），只留日志。
            // 这是当前架构的已知限制，见 README 的"已知限制"。
            Log.d(TAG, "Flutter 侧未监听，本次只记录日志")
            return
        }

        // 5) EventSink 必须在主线程调用
        mainHandler.post {
            try {
                eventSink?.success(payload)
            } catch (e: Exception) {
                Log.e(TAG, "推送事件到 Flutter 失败: ${e.message}", e)
            }
        }
    }

    // 通知被移除时不用管，这里留个空实现说明一下（不覆盖也能跑）
    override fun onNotificationRemoved(sbn: StatusBarNotification?) {
        // no-op
    }
}
''',
    # ----------------------------------------------------------------------
    '.github/workflows/build.yml': r'''# .github/workflows/build.yml
#
# GitHub Actions 云端打包：push 到 main/master、提 PR、打 tag 或手动触发，
# 都会在云端跑一次 flutter build apk --release，产物挂在 Actions 的 Artifacts 里。
#
# 用法：
#   1. 把本工程推到 GitHub（scaffold_ledger.py 和本文件必须一起推上去）
#   2. push 后到仓库的 Actions 页面看 "build-apk" 这个 workflow
#   3. 跑完后在对应 run 底部下载 ledger-release-apk
#
# 说明：仓库里不需要提交 android/gradle wrapper 等平台壳文件，
#       workflow 会先 flutter create 生成，再用 scaffold_ledger.py --force 覆盖成业务代码。

name: build-apk

on:
  push:
    branches: [main, master]
    tags: ['v*']
  pull_request:
  workflow_dispatch: # 支持网页上手动点 "Run workflow"

permissions:
  contents: read

jobs:
  build-apk:
    name: Build release APK
    runs-on: ubuntu-latest
    timeout-minutes: 40

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Flutter
        uses: subosito/flutter-action@v2
        with:
          # 固定版本保证可重现；想跟最新版就把 flutter-version 删掉只留 channel: stable。
          # 注意：Flutter 3.29+ 会生成 build.gradle.kts，届时 android 下的 minSdk
          # 以 kts 里的 flutter.minSdkVersion 为准（默认 24），build.gradle 会被忽略。
          flutter-version: '3.24.5'
          channel: stable
          cache: true

      - name: Bootstrap Android 平台壳
        run: |
          flutter config --no-analytics
          # 只生成 android 平台；已存在的文件默认不覆盖
          flutter create --org com.example --project-name ledger --platforms=android .

      - name: 写入业务代码
        run: |
          python3 scaffold_ledger.py --force
          echo "---- 关键文件校验 ----"
          head -1 lib/main.dart
          grep -n "BIND_NOTIFICATION_LISTENER_SERVICE" android/app/src/main/AndroidManifest.xml
          grep -n "applicationId" android/app/build.gradle || true

      - name: 安装依赖
        run: flutter pub get

      - name: 静态检查（不阻塞打包）
        continue-on-error: true
        run: flutter analyze

      - name: 打包 release APK
        # 想要按 ABI 拆分成更小的包，把下面换成：
        #   flutter build apk --release --split-per-abi
        run: flutter build apk --release

      - name: 查看产物
        run: ls -lh build/app/outputs/flutter-apk/

      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: ledger-release-apk
          path: |
            build/app/outputs/flutter-apk/app-release.apk
            build/app/outputs/flutter-apk/*-release.apk
          if-no-files-found: error
          retention-days: 30
''',
    # ----------------------------------------------------------------------
    '.gitignore': r'''# .gitignore
# Flutter / Dart
.dart_tool/
.flutter-plugins
.flutter-plugins-dependencies
.packages
build/
pubspec.lock

# Android
android/.gradle/
android/local.properties
android/key.properties
android/app/*.jks
android/app/*.keystore
*.jks
*.keystore

# IDE
.idea/
*.iml
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db
''',
    # ----------------------------------------------------------------------
    'README.md': r'''# 记账本（Ledger）— 离线安卓记账 App

Flutter 3.x + Material 3，双录入：手动记账 + 微信/支付宝通知自动记账（进"待确认"）。
数据只存本机 `shared_preferences`（键 `records_v2`），不联网、不申请 INTERNET 权限。

## 一、目录结构

```
scaffold_ledger.py                       一键生成脚本（自包含，所有文件内容内联其中）
.github/workflows/build.yml              GitHub Actions 云打包配置
.gitignore
lib/
  main.dart                              App 入口 / 主题（seed = 0xFF007AFF）
  models/record.dart                     Record 模型 + 枚举 + JSON 序列化
  services/storage.dart                  持久化（load/save，读取失败返回空列表）
  services/payment_listener.dart         通道封装（MethodChannel + EventChannel）
  services/payment_parser.dart           通知文本解析（金额 / 收支 / 商户）
  screens/home_page.dart                 首页：汇总 + 列表 + 去重 + 自动入账
  screens/add_page.dart                  手动记账 / 编辑
  screens/pending_page.dart              待确认列表
android/app/src/main/AndroidManifest.xml
android/app/src/main/kotlin/com/example/ledger/MainActivity.kt
android/app/src/main/kotlin/com/example/ledger/PaymentNotificationService.kt
android/app/build.gradle                 补充：minSdk 21 / targetSdk 34
pubspec.yaml
```

## 二、一键生成脚本（最快路径）

`scaffold_ledger.py` 是自包含的：16 个文件的内容全部内联在里面，不联网、无第三方依赖，
只用 Python 3.7+ 标准库。它会自动建好 `lib/models`、`lib/services`、`lib/screens`、
`android/app/src/main/kotlin/com/example/ledger`、`.github/workflows` 等目录并写入文件。

```bash
# 1. 空目录里生成
mkdir ledger && cd ledger
python scaffold_ledger.py                 # 已存在的文件跳过
python scaffold_ledger.py --force         # 覆盖（会先备份成 .bak）
python scaffold_ledger.py --out myapp     # 指定输出目录
python scaffold_ledger.py --list          # 只打印清单
python scaffold_ledger.py --clean         # 撤销（删掉脚本写出的文件）

# 2. 补 Android 平台壳（gradle wrapper / res / 图标 / debug manifest）
flutter create --org com.example --project-name ledger --platforms=android .

# 3. 把业务代码覆盖回去（flutter create 会写默认的 main.dart / Manifest）
python scaffold_ledger.py --force

# 4. 跑
flutter pub get
flutter run
```

> 顺序很重要：**先 create 后 --force**。反过来也能用，只是 create 可能覆盖掉
> `lib/main.dart` 和 `AndroidManifest.xml`，再跑一次 `--force` 即可。

## 三、本地运行步骤（手动版）

### 1. 生成脚手架

```bash
# 在项目上一级目录执行，--org 决定默认包名，工程名 ledger 会变成 package:ledger
flutter create --org com.example --project-name ledger ledger
cd ledger
```

### 2. 覆盖文件

用本仓库的 `lib/`、`pubspec.yaml`、`android/app/src/main/AndroidManifest.xml`、
`android/app/src/main/kotlin/com/example/ledger/*.kt` 覆盖脚手架里的同名文件。
`flutter create` 会额外生成 `android/app/src/main/kotlin/com/example/ledger/MainActivity.kt`，
直接用本仓库的替换掉。

### 3. 改 minSdk / targetSdk

`android/app/build.gradle`（新版 Flutter 是 `build.gradle.kts`）：

```groovy
defaultConfig {
    minSdk = 21          // 新版 Flutter 默认 24，构建报错就改 24
    targetSdk = 34
}
```

### 4. 安装依赖并运行

```bash
flutter pub get
flutter run            # 连真机，或 flutter run --release
```

> 通知监听在模拟器上也能用，但微信/支付宝通常登不上，建议真机验证自动记账。

### 5. 改包名（可选，题目说你会自己改）

需要同时改 **4 处**，缺一不可：

1. `android/app/build.gradle` 的 `namespace` 和 `applicationId`
2. `android/app/src/main/kotlin/com/example/ledger/` 这个**目录路径**（挪到新包路径下）
3. `MainActivity.kt` 和 `PaymentNotificationService.kt` 里的 `package com.example.ledger`
4. 重装时先 `flutter clean`

Manifest 里的 `.MainActivity` / `.PaymentNotificationService` 是相对写法，不用改。

也可以一条命令搞定（保险起见先备份）：

```bash
flutter pub run change_app_package_name:main com.yourname.ledger
```

### 6. 手机开启"通知使用权"

1. 首次启动 App 会弹窗，点"去开启"（或点 AppBar 右上的小铃铛图标）
2. 系统路径一般是：**设置 → 通知与状态栏 → 通知使用权 / 通知监听**
   （部分 ROM：设置 → 应用 → 特殊应用权限 → 通知使用权）
3. 在列表里找到「记账本」，打开开关，弹窗确认"允许"
4. 回 App，铃铛图标消失即成功

验证自动记账：

```bash
adb logcat -s PayNotif          # 只看通知原文
adb logcat -s flutter           # 看 Dart 侧 [自动记账] 日志
```

用微信/支付宝付 0.01 元 → Logcat 出现 `raw = ...` → App 首页出现一条黄色「待确认」。

### 7. 打包

```bash
flutter build apk --release
# 产物：build/app/outputs/flutter-apk/app-release.apk

# 按 ABI 拆分（体积更小）
flutter build apk --release --split-per-abi
```

## 四、云端打包（GitHub Actions）

`.github/workflows/build.yml` 已配好，push 即可自动出包，不用本地装 Flutter/Android SDK。

```bash
git init && git add . && git commit -m "feat: 记账本"
git remote add origin git@github.com:<你的账号>/<仓库名>.git
git push -u origin main
```

流程：`checkout` → JDK 17 → Flutter 3.24.5（固定版本保证可重现）→
`flutter create` 生成 Android 壳 → `python3 scaffold_ledger.py --force` 写业务代码 →
`pub get` → `flutter analyze`（仅告警，不阻塞）→ `build apk --release` →
上传 `ledger-release-apk`。

在 Actions 页面点进任意一次 run，底部 **Artifacts** 就能下载 APK。
也支持网页手动触发（workflow_dispatch）和打 tag（`v1.0.0`）。

- 想把版本换成最新：把 `flutter-version: '3.24.5'` 删掉，只留 `channel: stable`
- 想要按 ABI 拆分小包：`flutter build apk --release --split-per-abi`
- 想签正式包：把 keystore 放进 GitHub Secrets 并在 `android/app/build.gradle` 里引用

## 五、已知限制与下一步优化

**1. 通知文案会变，正则一定会漂移。**
微信/支付宝的通知文案随版本、灰度、机型（尤其 MIUI/ColorOS 的折叠通知）不同而不同。
`payment_parser.dart` 的金额正则和关键词需要拿真机 `PayNotif` 日志反复校准。
解析不出来时**故意返回 null 不入账**，不会瞎猜错账。

**2. App 进程被杀时，自动记账会"只打日志不入库"。**
`NotificationListenerService` 是系统保活的，但 Flutter 引擎不在时 `EventSink` 为空，
事件只能写 Logcat。想彻底解决需要：前台服务 + 本地缓存队列（原生侧先落盘，Dart 启动时回灌）。

**3. 去重是内存级、30 秒时间桶的粗粒度方案。**
同一笔支付若在 30 秒后被重复推送仍会重复入账；App 重启后 Set 清空。更稳的做法是把
`source + 金额 + 通知时间去重`落盘，或用 `StatusBarNotification.getKey()` 做唯一键回传。

**4. 存储是全量 JSON，条目多了会慢。**
`shared_preferences` 每次保存都要序列化整表，几千条以后首页会有可感知的卡顿。
下一步换 `sqflite` / `drift`，配合分页查询。

**5. 自动记账不推断分类。**
分类直接填商户名（如"星巴克"），需要用户手动改成"餐饮"。
可以加一层商户→分类的本地映射表，命中就自动归类。

**6. 缺统计报表。**
目前只有总收入/总支出/结余。下一步：按月分组、分类饼图、预算提醒、CSV 导出/备份。

## 六、验收自测清单

- [ ] `flutter pub get` 无依赖冲突
- [ ] `flutter run` 启动，手动记一笔支出/收入 → 列表 + 汇总正确
- [ ] 左滑删除 → 有撤销
- [ ] 杀掉 App 重开 → 数据仍在
- [ ] 开启通知使用权 → 付 0.01 元 → Logcat 有 `PayNotif` → 待确认多一条
- [ ] 待确认里"确认入账" → 黄色标签消失、计入汇总；"全部确认"生效
- [ ] `flutter build apk --release` 出包，装到手机上仍能自动记账
''',
}


# =============================================================================
# 生成逻辑
# =============================================================================


def _force_utf8_stdout() -> None:
    """Windows 控制台默认 GBK，输出中文/符号可能炸，这里强制 UTF-8。"""
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        if sys.stderr.encoding and sys.stderr.encoding.lower().replace("-", "") != "utf8":
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


def _print_plan() -> None:
    print("将要写出的文件（{} 个）：".format(len(FILES)))
    for rel in FILES:
        print("  " + rel)


def _write_all(root: Path, force: bool) -> int:
    created: list[str] = []
    skipped: list[str] = []
    backed_up: list[str] = []

    for rel, content in FILES.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            if not force:
                skipped.append(rel)
                continue
            old = target.read_text(encoding="utf-8", errors="replace")
            if old == content:
                skipped.append(rel)
                continue
            backup = target.with_suffix(target.suffix + ".bak")
            shutil.copy2(target, backup)
            backed_up.append(str(backup.relative_to(root)))

        # newline="\n" 保证在 Windows 上也写出 LF，跟 Flutter 工具链一致
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        created.append(rel)

    print()
    print("=" * 66)
    print("目录：{}".format(root))
    print("新建/覆盖：{} 个    跳过（已存在）：{} 个    备份：{} 个".format(
        len(created), len(skipped), len(backed_up)))
    print("=" * 66)
    for rel in created:
        print("  [OK]   " + rel)
    for rel in skipped:
        print("  [SKIP] " + rel + "（已存在，加 --force 覆盖）")
    for rel in backed_up:
        print("  [BAK]  " + rel)

    print()
    print("下一步：")
    print("  1) flutter create --org com.example --project-name ledger --platforms=android .")
    print("     （只为生成 android 平台壳：gradle wrapper / res / 图标）")
    print("  2) python scaffold_ledger.py --force      # 把业务代码覆盖回去")
    print("  3) flutter pub get")
    print("  4) flutter run                            # 或 flutter run --release")
    print("  5) flutter build apk --release            # 产物在 build/app/outputs/flutter-apk/")
    print()
    print("提醒：手机上要手动开启「通知使用权」，自动记账才能工作。")
    return 0


def _clean(root: Path) -> int:
    removed = 0
    for rel in FILES:
        target = root / rel
        if target.exists():
            target.unlink()
            removed += 1
            print("  [DEL] " + rel)
        bak = target.with_suffix(target.suffix + ".bak")
        if bak.exists():
            bak.unlink()
    # 清理空目录（从深到浅）
    dirs = sorted({(root / rel).parent for rel in FILES}, key=lambda p: len(p.parts), reverse=True)
    for d in dirs:
        try:
            if d.exists() and d != root and not any(d.iterdir()):
                d.rmdir()
                print("  [RMDIR] " + str(d.relative_to(root)))
        except Exception:
            pass
    print("已删除 {} 个文件".format(removed))
    return 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="生成记账本 Flutter 安卓工程（离线、自包含）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--out", default=".", help="输出目录，默认当前目录")
    parser.add_argument("--force", action="store_true", help="覆盖已存在文件（自动备份 .bak）")
    parser.add_argument("--list", action="store_true", help="只打印文件清单，不写盘")
    parser.add_argument("--clean", action="store_true", help="删除本脚本写出的文件")
    args = parser.parse_args(argv)

    root = Path(args.out).expanduser().resolve()

    if args.list:
        _print_plan()
        return 0

    if args.clean:
        return _clean(root)

    root.mkdir(parents=True, exist_ok=True)
    return _write_all(root, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
