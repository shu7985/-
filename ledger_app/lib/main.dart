// lib/main.dart
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
