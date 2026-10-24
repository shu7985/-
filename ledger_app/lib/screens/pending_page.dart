// lib/screens/pending_page.dart
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
