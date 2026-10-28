"""build_message: la burbuja de chat viaja como mensaje solo-datos."""

from app.push import fcm


def test_normal_message_has_notification_block():
    msg = fcm.build_message("t" * 12, "Hola", "Cuerpo", {"kind": "reminder"}, fcm.CHANNEL_SILENT, False)["message"]
    assert msg["notification"] == {"title": "Hola", "body": "Cuerpo"}
    assert msg["android"]["notification"]["channel_id"] == fcm.CHANNEL_SILENT
    assert "bubble" not in msg["data"]


def test_bubble_message_is_data_only():
    msg = fcm.build_message("t" * 12, "Hola", "Cuerpo", {"kind": "reminder"}, fcm.CHANNEL_SOUND, True)["message"]
    assert "notification" not in msg
    assert msg["data"] == {"kind": "reminder", "bubble": "1", "title": "Hola", "body": "Cuerpo", "sound": "1"}
    assert msg["android"] == {"priority": "high"}


def test_bubble_message_silent_flag():
    msg = fcm.build_message("t" * 12, "Hola", "Cuerpo", None, fcm.CHANNEL_SILENT, True)["message"]
    assert msg["data"]["sound"] == "0"


def test_focus_message_is_data_only():
    msg = fcm.build_focus_message("t" * 12, True)["message"]
    assert msg["data"] == {"focus": "on"} and "notification" not in msg
    assert fcm.build_focus_message("t" * 12, False)["message"]["data"] == {"focus": "off"}
