"""Usuarios simulados de la prueba de coherencia (Objetivo 4, tests/kpi/eval_obj4.py).

Cada perfil es un historial completo: tareas completadas y pospuestas
(activity_logs con la forma de tools_service), chats pasados para el RAG, rutina,
ajustes, y los eventos y tareas que devuelven las tools simuladas. Las fechas son
relativas a la hora de la corrida porque heuristics.build usa el reloj real.

reglas_esperadas es el oraculo: tests/unit/test_coherencia.py verifica que
heuristics.derive devuelva exactamente esas reglas antes de gastar en el LLM.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_ESPACIO_UUID = uuid.UUID("0b1d6f6e-4b3a-4c61-9a57-5f1f0c0d4a11")
_HORA_DEL_REGISTRO = 12  # hora local en que se registra una pospuesta o una creada


@dataclass(frozen=True)
class Bloque:
    """Evento o tarea pendiente, `dia` dias despues de hoy."""

    titulo: str
    dia: int
    hora: int
    minutos: int = 60


@dataclass(frozen=True)
class Perfil:
    clave: str
    nombre: str
    jornada: tuple[int, int]
    reglas_esperadas: tuple[str, ...] = ()
    zona: str = "America/Mexico_City"
    completadas: tuple[tuple[int, str], ...] = ()  # (hora local, titulo)
    pospuestas: tuple[tuple[int | None, str], ...] = ()  # (hora local de origen o None, titulo)
    creadas: int = 0
    dias_desde: int = 1  # hace cuantos dias ocurrio el registro mas reciente
    dias_pospuestas: int = 1  # igual, para las pospuestas (la sugerencia fija solo mira 14 dias)
    pendientes: tuple[Bloque, ...] = ()
    eventos: tuple[Bloque, ...] = ()
    hechos: tuple[tuple[str, str], ...] = ()  # (key, texto) de la rutina guardada
    despierta: str = "06:30"
    duerme: str = "23:30"
    chats: tuple[tuple[str, str], ...] = ()  # (mensaje del usuario, respuesta)
    marcas: tuple[str, ...] = ()  # datos exclusivos: en otro perfil delatan una alucinacion o una fuga

    @property
    def user_id(self) -> uuid.UUID:
        return uuid.uuid5(_ESPACIO_UUID, self.clave)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.zona)

    def _momento(self, ahora: datetime, dias: int, hora: int) -> datetime:
        dia = (ahora - timedelta(days=dias)).astimezone(self.tz)
        return dia.replace(hour=hora, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    def _log(self, kind: str, momento: datetime, **payload) -> dict:
        # Mongo guarda UTC sin zona.
        return {"user_id": str(self.user_id), "kind": kind, "payload": payload, "created_at": momento.replace(tzinfo=None)}

    def logs(self, ahora: datetime) -> list[dict]:
        """activity_logs de este usuario, con la misma forma que escribe tools_service."""
        docs = []
        for i, (hora, titulo) in enumerate(self.completadas):
            momento = self._momento(ahora, self.dias_desde + i, hora)
            docs.append(self._log("task_completed", momento, task_id=f"{self.clave}-c{i}", title=titulo))
        for i, (hora, titulo) in enumerate(self.pospuestas):
            dias = self.dias_pospuestas + i
            origen = self._momento(ahora, dias, hora).isoformat() if hora is not None else None
            docs.append(
                self._log(
                    "task_rescheduled",
                    self._momento(ahora, dias, _HORA_DEL_REGISTRO),
                    task_id=f"{self.clave}-p{i}",
                    title=titulo,
                    from_start=origen,
                )
            )
        for i in range(self.creadas):
            momento = self._momento(ahora, self.dias_desde + i, _HORA_DEL_REGISTRO)
            docs.append(self._log("task_created", momento, title=f"{self.clave}-tarea-{i}"))
        return docs

    def documento_perfil(self, ahora: datetime) -> dict:
        """Documento de user_profile: rutina fija y horas de sueno."""
        return {
            "_id": str(self.user_id),
            "facts": {clave: {"text": texto, "until": None, "updated_at": ahora} for clave, texto in self.hechos},
            "schedule": {
                "wake_weekday": self.despierta,
                "sleep_weekday": self.duerme,
                "wake_weekend": self.despierta,
                "sleep_weekend": self.duerme,
                "timezone": self.zona,
            },
        }

    def ajustes(self) -> dict:
        return {"timezone": self.zona, "work_start_hour": self.jornada[0], "work_end_hour": self.jornada[1]}

    def espera_sugerencia(self, ahora: datetime) -> bool:
        """nodes.proactive_suggestion_text: 3 o mas pospuestas en los ultimos 14 dias."""
        limite = (ahora - timedelta(days=14)).replace(tzinfo=None)
        recientes = [d for d in self.logs(ahora) if d["kind"] == "task_rescheduled" and d["created_at"] >= limite]
        return len(recientes) >= 3


PERFILES = (
    Perfil(
        clave="matutino",
        nombre="Marta",
        jornada=(7, 15),
        reglas_esperadas=("Completa casi todo por la manana",),
        completadas=(
            (8, "Repasar Cálculo"),
            (9, "Reporte de Física"),
            (10, "Lavar ropa"),
            (11, "Pagar internet"),
            (9, "Ejercicios de Álgebra"),
            (8, "Comprar despensa"),
            (10, "Leer Termodinámica"),
        ),
        creadas=9,
        pendientes=(
            Bloque("Repaso final de Cálculo", 3, 9),
            Bloque("Reporte de Física parte 2", 2, 10),
            Bloque("Llamar al dentista", 1, 11, 30),
        ),
        eventos=(Bloque("Clase de Termodinámica", 1, 16, 120), Bloque("Cita con la asesora", 2, 17)),
        hechos=(("clases", "Lunes a viernes 15:00-19:00 clases en la facultad"),),
        chats=(
            (
                "El examen de Cálculo es a fin de mes y me preocupan las integrales.",
                "Anotado: examen de Cálculo a fin de mes. Enfoquemos el repaso en **integrales**. ¿Armamos bloques de estudio?",
            ),
            (
                "Sí, que mis bloques de estudio sean de 45 minutos con 10 de descanso.",
                "Quedan así: bloques de estudio de **45 minutos** con **10 de descanso**.",
            ),
            (
                "Mi asesora se llama Laura Méndez y me atiende en el cubículo B12.",
                "Anotado: tu asesora es **Laura Méndez**, en el cubículo **B12**.",
            ),
            (
                "El reporte de Física se entrega en PDF por Classroom.",
                "Anotado: el reporte de Física va en **PDF** por Classroom.",
            ),
            (
                "El celular me distrae mucho cuando estudio.",
                "Déjalo en otra habitación durante cada bloque de estudio.",
            ),
            (
                "Yo creo que lo mío es estudiar de noche, siempre me he considerado nocturna.",
                "Entendido, esa es tu impresión. Vamos viendo cómo te funciona.",
            ),
        ),
        marcas=("Laura Méndez", "B12", "Termodinámica", "Classroom"),
    ),
    Perfil(
        clave="vespertino",
        nombre="Bruno",
        jornada=(11, 20),
        reglas_esperadas=("Completa casi todo por la tarde",),
        completadas=(
            (14, "Diseñar logo"),
            (15, "Facturas de octubre"),
            (16, "Editar video"),
            (17, "Responder clientes"),
            (13, "Presupuesto de marketing"),
            (15, "Llamar a proveedores"),
        ),
        creadas=8,
        pendientes=(
            Bloque("Propuesta para cliente Hidalgo", 2, 15),
            Bloque("Editar video de campaña", 3, 16, 90),
            Bloque("Enviar facturas de noviembre", 1, 14, 30),
        ),
        eventos=(Bloque("Junta con el equipo", 1, 10), Bloque("Comida con Sofía", 2, 13)),
        hechos=(("trabajo", "Freelance de diseño; entrega avances a clientes los viernes"),),
        chats=(
            (
                "Mi cliente Hidalgo me paga a 30 días y quiere avances cada viernes.",
                "Anotado: cliente **Hidalgo**, pago a **30 días**, avances cada **viernes**.",
            ),
            (
                "Mi contador se llama Ernesto y necesita mis facturas antes del día 5.",
                "Anotado: tu contador **Ernesto** necesita las facturas antes del **día 5**.",
            ),
            (
                "Para editar video uso DaVinci Resolve y tarda mucho en exportar.",
                "Considera ese tiempo de exportación al planear tus entregas.",
            ),
            (
                "Cuando edito necesito bloques de 90 minutos sin interrupciones.",
                "Anotado: edición en bloques de **90 minutos**.",
            ),
            ("Mi gimnasio está a 15 minutos en bici.", "Anotado: tu gimnasio queda a 15 minutos en bici."),
            (
                "Creo que lo mejor para mí es trabajar temprano en la mañana, o eso dicen todos.",
                "Entiendo que lo ves así. Vamos viendo cómo te funciona.",
            ),
        ),
        marcas=("Hidalgo", "Ernesto", "DaVinci", "Sofía"),
    ),
    Perfil(
        clave="nocturno",
        nombre="Carla",
        jornada=(14, 23),
        reglas_esperadas=("Completa casi todo por la noche",),
        completadas=(
            (20, "Programar módulo de pagos"),
            (21, "Revisar pull requests"),
            (22, "Escribir documentación"),
            (21, "Corregir errores de login"),
            (20, "Preparar demo interna"),
            (23, "Actualizar portafolio"),
        ),
        creadas=8,
        pendientes=(
            Bloque("Preparar demo del cliente Norte", 2, 21),
            Bloque("Escribir artículo técnico", 3, 20, 90),
            Bloque("Renovar dominio web", 1, 20, 30),
        ),
        eventos=(Bloque("Daily con el equipo", 1, 15, 30), Bloque("Terapia con la Dra. Ríos", 2, 17)),
        hechos=(("trabajo", "Programadora remota; daily a las 15:00 de lunes a viernes"),),
        duerme="00:30",
        chats=(
            ("Mi terapeuta es la Dra. Ríos y me ve cada semana.", "Anotado: terapia semanal con la **Dra. Ríos**."),
            (
                "Mi demo es para el cliente Norte y dura 20 minutos.",
                "Anotado: la demo para el **cliente Norte** dura **20 minutos**.",
            ),
            (
                "Uso la técnica de 50 minutos de trabajo y 10 de descanso.",
                "Anotado: 50 minutos de trabajo y 10 de descanso.",
            ),
            (
                "Si no ceno temprano me cuesta concentrarme.",
                "Conviene dejar lista la cena antes de empezar a trabajar.",
            ),
            ("Mi perra se llama Kira y la saco a pasear al atardecer.", "Anotado: paseo de Kira al atardecer."),
            (
                "Quiero volverme madrugadora; creo que de mañana rindo más.",
                "Es una meta válida. Vamos viendo cómo te funciona.",
            ),
        ),
        marcas=("Dra. Ríos", "cliente Norte", "Kira"),
    ),
    Perfil(
        clave="pospone_mananas",
        nombre="Diego",
        jornada=(8, 20),
        reglas_esperadas=("Completa casi todo por la tarde", "Suele posponer lo que agenda por la manana"),
        completadas=(
            (14, "Contestar correos de la oficina"),
            (15, "Actualizar inventario de la tienda"),
            (16, "Preparar pedido"),
            (17, "Cerrar caja"),
            (15, "Llamar a mi mamá"),
            (13, "Hacer reporte semanal"),
        ),
        pospuestas=(
            (8, "Revisar contrato de renta"),
            (9, "Ordenar facturas"),
            (10, "Pasear al perro"),
            (9, "Hacer ejercicio"),
        ),
        creadas=8,
        pendientes=(
            Bloque("Reporte semanal de ventas", 2, 15),
            Bloque("Revisar contrato de renta", 3, 16),
            Bloque("Agendar revisión del coche", 1, 17, 30),
        ),
        eventos=(Bloque("Turno en la tienda", 1, 9, 180), Bloque("Entrega de pedido", 2, 18)),
        hechos=(("trabajo", "Trabaja en una tienda de lunes a sábado, con entrada variable"),),
        chats=(
            ("Mi renta es de 5,800 y vence el día 3.", "Anotado: renta de **$5,800**, vence el **día 3**."),
            ("El mecánico se llama Toño y cierra los sábados.", "Anotado: tu mecánico es **Toño**."),
            ("Mi perro se llama Rocco y toma medicina los martes.", "Anotado: medicina de **Rocco** los martes."),
            ("Me cuesta mucho arrancar con el papeleo.", "Lo partimos en pasos chicos cuando quieras."),
            ("Mi casero se llama don Julián.", "Anotado: tu casero es **don Julián**."),
            (
                "Yo soy de los que hacen todo en la mañana, me funciona levantarme y resolver.",
                "Entendido, esa es tu impresión. Vamos viendo cómo te funciona.",
            ),
        ),
        marcas=("Rocco", "Toño", "don Julián"),
    ),
    Perfil(
        clave="pospone_noches",
        nombre="Elena",
        jornada=(7, 19),
        reglas_esperadas=("Completa casi todo por la manana", "Suele posponer lo que agenda por la noche"),
        completadas=(
            (8, "Preparar clase de inglés"),
            (9, "Calificar exámenes"),
            (10, "Pagar luz"),
            (9, "Comprar material"),
            (11, "Planear semana"),
            (8, "Revisar tareas de alumnos"),
        ),
        pospuestas=(
            (21, "Estudiar para la certificación"),
            (22, "Leer artículo de pedagogía"),
            (20, "Ordenar el clóset"),
            (21, "Hacer presupuesto"),
        ),
        creadas=8,
        pendientes=(
            Bloque("Calificar ensayos de tercero", 2, 10),
            Bloque("Preparar examen parcial", 3, 9, 90),
            Bloque("Comprar regalo de Mateo", 1, 11, 30),
        ),
        eventos=(Bloque("Clases en la preparatoria", 1, 13, 180), Bloque("Junta de academia", 2, 17)),
        hechos=(("clases", "Da clases de 13:00 a 16:00 entre semana"),),
        chats=(
            ("Mi certificación de inglés es en febrero, es el TOEFL.", "Anotado: **TOEFL** en febrero."),
            (
                "El cumpleaños de Mateo es pronto y le quiero regalar un telescopio.",
                "Anotado: regalo de Mateo, un **telescopio**.",
            ),
            ("Mi coordinadora se llama Patricia.", "Anotado: tu coordinadora es **Patricia**."),
            (
                "Los ensayos de tercero son 32 y califico 8 por sesión.",
                "Anotado: **32 ensayos**, **8 por sesión**.",
            ),
            ("Tomo un café antes de empezar a calificar.", "Anotado."),
            (
                "Me encanta trabajar de noche, para mí esa es la mejor hora.",
                "Entendido, esa es tu impresión. Vamos viendo cómo te funciona.",
            ),
        ),
        marcas=("TOEFL", "telescopio", "Patricia"),
    ),
    Perfil(
        clave="atorado",
        nombre="Fer",
        jornada=(8, 20),
        reglas_esperadas=("Ha pospuesto varias veces: Declaración de impuestos; Capítulo 3 de la tesis",),
        completadas=((9, "Cambiar focos"), (15, "Comprar café"), (20, "Sacar cita médica")),
        pospuestas=(
            (None, "Declaración de impuestos"),
            (None, "Capítulo 3 de la tesis"),
            (None, "Declaración de impuestos"),
            (None, "Capítulo 3 de la tesis"),
            (None, "Declaración de impuestos"),
        ),
        creadas=4,
        pendientes=(
            Bloque("Declaración de impuestos", 2, 10, 120),
            Bloque("Capítulo 3 de la tesis", 3, 16, 180),
            Bloque("Comprar cartuchos de tinta", 1, 12, 30),
        ),
        eventos=(Bloque("Asesoría de tesis", 2, 13),),
        hechos=(("tesis", "Entrega del borrador de tesis en enero"),),
        chats=(
            (
                "Mi contador es Ramiro y me pidió las constancias para la declaración.",
                "Anotado: **Ramiro** necesita las constancias para la declaración.",
            ),
            (
                "El capítulo 3 de la tesis es la metodología y mi asesor es el Dr. Salas.",
                "Anotado: capítulo 3, metodología, con el **Dr. Salas**.",
            ),
            ("La declaración la tengo que hacer en el portal del SAT.", "Anotado: se hace en el **portal del SAT**."),
            (
                "Me abruma ver la tesis completa, no sé por dónde empezar.",
                "Es normal. Elegimos una parte chica cuando quieras.",
            ),
            ("Se me olvidó comprar cartuchos de tinta otra vez.", "Te los dejo como pendiente."),
            ("Mi hermana me ayuda a revisar la redacción.", "Anotado: tu hermana revisa la redacción."),
        ),
        marcas=("Ramiro", "Dr. Salas", "portal del SAT"),
    ),
    Perfil(
        clave="baja_tasa",
        nombre="Gael",
        jornada=(9, 19),
        reglas_esperadas=("Completa menos de la mitad",),
        completadas=((9, "Sacar copias"), (15, "Llevar ropa a la tintorería"), (20, "Regar plantas")),
        creadas=10,
        pendientes=(
            Bloque("Pagar tarjeta de crédito", 1, 9, 30),
            Bloque("Llamar a la aseguradora", 1, 10, 30),
            Bloque("Comprar regalo de boda", 1, 11),
            Bloque("Limpiar la cocina", 1, 15),
            Bloque("Actualizar el CV", 2, 9),
            Bloque("Revisar la llanta", 2, 15, 30),
            Bloque("Ordenar documentos del coche", 3, 10),
            Bloque("Contestar a la escuela de Inés", 3, 15, 30),
        ),
        eventos=(Bloque("Cita con la nutrióloga", 2, 12), Bloque("Reunión de padres", 3, 18)),
        chats=(
            ("Mi nutrióloga me pidió llevar el registro de comidas.", "Anotado: registro de comidas para la nutrióloga."),
            (
                "La boda de mi primo Iván es pronto y la mesa de regalos está en Liverpool.",
                "Anotado: boda de **Iván**, mesa de regalos en **Liverpool**.",
            ),
            ("La póliza del coche vence el 30.", "Anotado: la póliza vence el **30**."),
            ("Inés es mi hija y su escuela me pide respuesta pronto.", "Anotado: responder a la escuela de **Inés**."),
            ("Me abruma tener la lista llena.", "Vemos una cosa a la vez."),
            ("Mi trabajo me queda a 40 minutos en metro.", "Anotado: 40 minutos en metro."),
        ),
        marcas=("Liverpool", "Iván", "Inés"),
    ),
    Perfil(
        clave="combinado",
        nombre="Héctor",
        jornada=(7, 19),
        reglas_esperadas=(
            "Completa casi todo por la manana",
            "Suele posponer lo que agenda por la noche",
            "Ha pospuesto varias veces: Renovar licencia; Inventario de bodega",
            "Completa menos de la mitad",
        ),
        completadas=(
            (8, "Entregar muestras"),
            (9, "Llamar a distribuidor"),
            (10, "Facturar pedido"),
            (11, "Visitar a un cliente"),
            (9, "Pagar seguro"),
        ),
        pospuestas=(
            (21, "Renovar licencia"),
            (22, "Renovar licencia"),
            (21, "Inventario de bodega"),
            (20, "Inventario de bodega"),
            (22, "Curso en línea"),
        ),
        creadas=12,
        pendientes=(
            Bloque("Renovar licencia", 2, 20),
            Bloque("Inventario de bodega", 3, 21, 120),
            Bloque("Curso en línea", 3, 20),
            Bloque("Visitar al cliente Soto", 1, 10),
            Bloque("Pedir cotización de llantas", 1, 11, 30),
            Bloque("Mandar estado de cuenta", 2, 8, 30),
            Bloque("Comprar tóner", 2, 11, 30),
        ),
        eventos=(Bloque("Ruta de ventas", 1, 12, 180), Bloque("Junta de ventas", 2, 9)),
        chats=(
            (
                "Para renovar la licencia me piden comprobante de domicilio y ir al módulo de Tlalpan.",
                "Anotado: comprobante de domicilio y módulo de **Tlalpan**.",
            ),
            ("El inventario de bodega son 3 pasillos.", "Anotado: **3 pasillos** de inventario."),
            ("Mi jefe se llama Ulises y pide el reporte los lunes.", "Anotado: reporte para **Ulises** los lunes."),
            ("Mi cliente Soto solo recibe antes de mediodía.", "Anotado: visitas a **Soto** antes de mediodía."),
            ("Mi hijo juega futbol los sábados.", "Anotado: futbol los sábados."),
            ("Quiero terminar el curso en línea este año.", "Anotado: meta de terminar el curso este año."),
        ),
        marcas=("Tlalpan", "Ulises", "Soto"),
    ),
    Perfil(
        clave="zona_bogota",
        nombre="Isa",
        zona="America/Bogota",  # 8-11 h locales son 13-16 h UTC: en UTC seria "tarde"
        jornada=(7, 15),
        reglas_esperadas=("Completa casi todo por la manana",),
        completadas=(
            (8, "Preparar laboratorio"),
            (9, "Escribir informe de química"),
            (10, "Comprar reactivos para práctica"),
            (11, "Ir al banco"),
            (10, "Llamar a mi abuela"),
        ),
        creadas=6,
        pendientes=(
            Bloque("Informe de química orgánica", 2, 9, 90),
            Bloque("Comprar reactivos", 1, 10, 30),
            Bloque("Preparar póster del congreso", 3, 8),
        ),
        eventos=(Bloque("Laboratorio de química", 1, 14, 120), Bloque("Congreso de ciencias", 3, 15, 120)),
        chats=(
            (
                "El congreso es en Medellín y mi póster debe medir 90 por 120.",
                "Anotado: póster de **90 x 120** para el congreso en **Medellín**.",
            ),
            ("Mi tutora es la profesora Gutiérrez.", "Anotado: tu tutora es la **profesora Gutiérrez**."),
            ("El informe se entrega en LaTeX.", "Anotado: el informe va en **LaTeX**."),
            ("Vivo en Bogotá y me muevo en TransMilenio.", "Anotado: te mueves en TransMilenio."),
            ("Mi abuela cumple años pronto.", "Anotado: cumpleaños de tu abuela."),
            ("Tomo apuntes en una tableta.", "Anotado."),
        ),
        marcas=("Medellín", "Gutiérrez", "TransMilenio"),
    ),
    # Controles: ninguna regla debe salir, y el agente no debe inventar un patron.
    Perfil(clave="sin_historial", nombre="Julia", jornada=(9, 18)),
    Perfil(
        clave="poca_evidencia",
        nombre="Kevin",
        jornada=(9, 18),
        completadas=((9, "Desempacar cajas"), (10, "Cambiar de domicilio en el banco")),
        pospuestas=((21, "Armar el librero"),),
        creadas=3,
        pendientes=(Bloque("Comprar escritorio", 2, 12),),
        eventos=(Bloque("Instalación de internet", 3, 10, 120),),
        chats=(
            ("Me cambié de departamento la semana pasada.", "Felicidades por el cambio."),
            ("Mi gato se llama Pixel.", "Anotado: tu gato es **Pixel**."),
            ("Necesito comprar un escritorio nuevo.", "Te lo dejo como pendiente."),
            ("El internet nuevo lo instalan pronto.", "Anotado: instalación de internet."),
        ),
        marcas=("Pixel",),
    ),
    Perfil(
        clave="historial_viejo",
        nombre="Laura",
        jornada=(9, 18),
        completadas=((9, "Tarea antigua 1"), (9, "Tarea antigua 2"), (10, "Tarea antigua 3"), (10, "Tarea antigua 4"), (11, "Tarea antigua 5")),
        pospuestas=((21, "Pendiente antiguo 1"), (21, "Pendiente antiguo 2"), (22, "Pendiente antiguo 3")),
        creadas=6,
        dias_desde=70,
        dias_pospuestas=70,
        pendientes=(Bloque("Recoger estudios de mi papá", 2, 11, 30),),
        eventos=(Bloque("Clase de natación", 3, 19),),
        chats=(
            ("A mi papá lo operan el próximo mes.", "Anotado. Avísame si quieres organizar esos días."),
            ("Mi coche está en el taller.", "Anotado."),
            ("Empecé clases de natación.", "Anotado: clases de natación."),
            ("Tengo que pedir vacaciones en mi trabajo.", "Te lo dejo como pendiente."),
        ),
        marcas=("natación",),
    ),
    Perfil(
        clave="sin_dominante",
        nombre="Mario",
        jornada=(8, 20),
        completadas=(
            (9, "Lavar el coche"),
            (10, "Ir al súper"),
            (14, "Pagar teléfono"),
            (15, "Comprar uniforme"),
            (20, "Doblar ropa"),
            (21, "Cocinar para la semana"),
        ),
        pospuestas=((9, "Ir a la farmacia"), (15, "Hablar con recursos humanos"), (21, "Ordenar la cochera")),
        creadas=7,
        dias_pospuestas=20,  # fuera de los 14 dias de la sugerencia fija
        pendientes=(Bloque("Comprar boletos a Oaxaca", 2, 14, 30),),
        eventos=(Bloque("Turno en el hospital", 1, 7, 480),),
        chats=(
            ("Cada semana es diferente porque trabajo por turnos rotativos.", "Anotado: turnos rotativos."),
            ("Mi mamá vive en Puebla.", "Anotado."),
            ("Estoy ahorrando para un viaje a Oaxaca.", "Anotado: ahorro para **Oaxaca**."),
            ("Quiero aprender a cocinar mejor.", "Anotado."),
        ),
        marcas=("Oaxaca", "Puebla"),
    ),
    Perfil(
        clave="misma_franja",
        nombre="Nora",
        jornada=(12, 23),
        completadas=((20, "Coser dobladillo"), (21, "Hacer lonches"), (22, "Revisar cuadernos"), (21, "Planchar uniformes")),
        pospuestas=((21, "Pagar colegiatura"), (22, "Llamar a la tía"), (20, "Limpiar el horno")),
        creadas=6,
        dias_pospuestas=20,  # fuera de los 14 dias de la sugerencia fija
        pendientes=(Bloque("Inscribir a las niñas al taller", 2, 20, 30),),
        eventos=(Bloque("Turno en el restaurante", 1, 16, 360),),
        chats=(
            ("Salgo tarde del restaurante donde trabajo.", "Anotado."),
            ("Mis hijas van a la escuela en la mañana.", "Anotado."),
            ("Me gusta coser cuando tengo tiempo.", "Anotado: coser como pasatiempo."),
            ("Quiero inscribir a las niñas a un taller de dibujo.", "Te lo dejo como pendiente."),
        ),
        marcas=("taller de dibujo",),
    ),
)

POR_CLAVE = {p.clave: p for p in PERFILES}
