"""Tras leer contenido de terceros (correos, invitaciones de calendario) las
tools de escritura quedan bloqueadas en ese turno."""

from app.clients.tools_client import TOOL_ROUTES, UNTRUSTED_TOOLS, WRITE_TOOLS


def test_correos_e_invitaciones_son_no_confiables():
    assert {"read_recent_emails", "list_events"} <= UNTRUSTED_TOOLS


def test_las_listas_solo_nombran_tools_reales():
    assert UNTRUSTED_TOOLS <= set(TOOL_ROUTES)
    assert WRITE_TOOLS <= set(TOOL_ROUTES)
