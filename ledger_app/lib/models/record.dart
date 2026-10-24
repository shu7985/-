// lib/models/record.dart
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
