// lib/services/storage.dart
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
