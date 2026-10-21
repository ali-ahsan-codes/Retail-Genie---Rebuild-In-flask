from retail_genie.extensions import db
from retail_genie.models import AuditEvent, Conversation, MessageRecipient


def test_message_threads_only_deliver_to_and_are_visible_to_selected_participants(app, client, create_user):
    sender_id = create_user("message.sender", role="salesperson", permissions=[])
    recipient_id = create_user("message.recipient", role="salesperson", permissions=[])
    create_user("message.outsider", role="salesperson", permissions=[])
    client.post("/login", data={"username": "message.sender", "password": "A-long-test-password-4!"})
    assert client.get("/messaging").status_code == 200
    assert client.get("/messaging/compose").status_code == 200
    created = client.post("/messaging/conversations", json={"subject": "Private thread", "recipient_ids": [recipient_id]})
    assert created.status_code == 201, created.get_json()
    conversation_id = created.get_json()["conversation"]["id"]
    sent = client.post(f"/messaging/conversations/{conversation_id}/messages", json={"content": "Only the selected recipient should get this."})
    assert sent.status_code == 201, sent.get_json()
    thread_page = client.get(f"/messaging/conversations/{conversation_id}")
    assert thread_page.status_code == 200 and b"Only the selected recipient" in thread_page.data
    client.post("/logout")
    client.post("/login", data={"username": "message.recipient", "password": "A-long-test-password-4!"})
    recipient_threads = client.get("/messaging/conversations")
    assert recipient_threads.status_code == 200
    assert any(row["id"] == conversation_id for row in recipient_threads.get_json()["conversations"])
    read = client.get(f"/api/v1/messaging/conversations/{conversation_id}/messages")
    assert read.status_code == 200 and len(read.get_json()["messages"]) == 1
    client.post("/logout")
    client.post("/login", data={"username": "message.outsider", "password": "A-long-test-password-4!"})
    outsider_threads = client.get("/messaging/conversations")
    assert outsider_threads.status_code == 200
    assert outsider_threads.get_json()["conversations"] == []
    denied = client.get(f"/api/v1/messaging/conversations/{conversation_id}/messages")
    assert denied.status_code == 403
    with app.app_context():
        assert MessageRecipient.query.filter_by(recipient_id=recipient_id).count() == 1
        assert MessageRecipient.query.filter_by(recipient_id=sender_id).count() == 0
        assert AuditEvent.query.filter(AuditEvent.action.in_(["messaging.conversation.created", "messaging.message.sent"])).count() == 2
        assert Conversation.query.count() == 1
