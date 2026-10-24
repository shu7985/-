// android/app/src/main/kotlin/com/example/ledger/MainActivity.kt
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
