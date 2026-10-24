// lib/services/payment_parser.dart
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
