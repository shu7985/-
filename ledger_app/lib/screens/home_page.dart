// lib/screens/home_page.dart
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
