import pytest
from fastapi.testclient import TestClient
from app.main import app

# Create a module-level TestClient for synchronous websocket tests
client = TestClient(app)

def test_websocket_ping():
    """Test basic ping-pong via WebSocket to ensure connection and router work."""
    with client.websocket_connect("/ws/test-ping-123") as websocket:
        websocket.send_json({"type": "ping"})
        data = websocket.receive_json()
        assert data["type"] == "pong"

def test_websocket_end_session():
    """Test ending a session immediately."""
    with client.websocket_connect("/ws/test-end-123") as websocket:
        websocket.send_json({"type": "end_session"})
        data = websocket.receive_json()
        assert data["type"] == "session_over"
