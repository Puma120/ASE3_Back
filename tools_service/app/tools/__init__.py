"""Definicion de las tools que el Microservicio del Agente puede invocar.

Cada tool envuelve un integrations/*_client.py con la logica de negocio
especifica para TDAH descrita en el plan (implementation_plan.md /
Plantilla_ASE_III): calendar_tool, tasks_tool, maps_tool, gmail_tool,
device_tool (alarmas nativas / DND, solo disponible desde front/mobile
en Android).
"""
