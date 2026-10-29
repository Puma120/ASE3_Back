"""Borrar eventos: una serie con su id, y un evento ya borrado cuenta como hecho."""

from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from app.integrations import calendar_client


def _service(monkeypatch, status=None):
    service = MagicMock()
    execute = service.events.return_value.delete.return_value.execute
    if status:
        execute.side_effect = HttpError(MagicMock(status=status), b"")
    monkeypatch.setattr(calendar_client, "_service", lambda credentials: service)
    return service


def test_borra_por_id_en_el_calendario_principal(monkeypatch):
    service = _service(monkeypatch)

    calendar_client.delete_event(object(), "serie123")

    service.events.return_value.delete.assert_called_once_with(calendarId="primary", eventId="serie123")


@pytest.mark.parametrize("status", [404, 410])
def test_un_evento_ya_borrado_no_es_error(monkeypatch, status):
    _service(monkeypatch, status)
    calendar_client.delete_event(object(), "x")


def test_otros_errores_de_google_si_se_propagan(monkeypatch):
    _service(monkeypatch, 403)
    with pytest.raises(HttpError):
        calendar_client.delete_event(object(), "x")
