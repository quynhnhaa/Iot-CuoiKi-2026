def test_health_reports_decision_logic(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    # Backend phai nap duoc logic quyet dinh tu nhanh AI trong cung repo.
    assert body['decision_logic'] == 'ok'
