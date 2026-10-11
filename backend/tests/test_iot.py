"""Local IoT endpoint tests, no hardware or internet required."""
from unittest.mock import patch

from fastapi.testclient import TestClient
import app
import iot_sensor

client = TestClient(app.app)
TOKEN = 'test-device-token-very-long-and-unique'


def test_status_offline_before_first_reading():
    with iot_sensor._lock:
        iot_sensor._reading = None
        iot_sensor._arrived_monotonic = None
    response = client.get('/api/iot/current')
    assert response.status_code == 200
    assert response.json()['online'] is False
    assert response.json()['temperature_c'] is None


def test_post_needs_device_token():
    with patch.object(iot_sensor, '_DEVICE_KEY', TOKEN):
        response = client.post('/api/iot/readings', json={'temperature_c': 32.3, 'humidity_percent': 29.2})
    assert response.status_code == 401


def test_valid_reading_can_be_seen():
    with patch.object(iot_sensor, '_DEVICE_KEY', TOKEN):
        received = client.post('/api/iot/readings', headers={'X-Device-Key': TOKEN},
                               json={'temperature_c': 32.3, 'humidity_percent': 29.2})
        assert received.status_code == 200
        reading = client.get('/api/iot/current').json()
    assert reading['online'] is True
    assert reading['temperature_c'] == 32.3
    assert reading['humidity_percent'] == 29.2
    assert reading['updated_at']


def test_reject_invalid_readings():
    with patch.object(iot_sensor, '_DEVICE_KEY', TOKEN):
        response = client.post('/api/iot/readings', headers={'X-Device-Key': TOKEN},
                               json={'temperature_c': 120, 'humidity_percent': 29.2})
    assert response.status_code == 422


def test_stale_reading_is_not_shown_as_live():
    with patch.object(iot_sensor, '_DEVICE_KEY', TOKEN):
        client.post('/api/iot/readings', headers={'X-Device-Key': TOKEN},
                    json={'temperature_c': 29.3, 'humidity_percent': 31.2})
        with iot_sensor._lock:
            iot_sensor._arrived_monotonic -= 30
        response = client.get('/api/iot/current')
    assert response.status_code == 200
    assert response.json()['online'] is False
    assert response.json()['temperature_c'] is None
