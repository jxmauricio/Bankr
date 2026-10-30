from app.integrations import apns


def test_send_alert_skips_without_credentials():
    assert apns.send_alert("aaaaaaaaaaaaaaaa", "Title", "Body") == apns.SKIPPED
