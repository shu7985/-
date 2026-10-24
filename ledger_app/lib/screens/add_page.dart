// lib/screens/add_page.dart
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
