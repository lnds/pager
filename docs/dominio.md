# Dominio

Pager gestiona incidentes de producción: algo se rompió en un servicio, alguien de guardia
recibe el aviso, el equipo lo investiga, lo mitiga, lo resuelve y escribe un post-mortem.

## Glosario

| Término | Significado |
|---|---|
| **Servicio** | Un sistema en producción, registrado en el catálogo con su equipo y su SLO. |
| **Turno de guardia** | Una persona a cargo de un servicio entre dos fechas, ambas incluidas. |
| **Incidente** | Una degradación de un servicio, con título, severidad y estado. |
| **Severidad** | De `1` (SEV1, la más grave: caída total o pérdida de datos) a `4` (SEV4, molestia menor). |
| **Bitácora** | La secuencia de eventos de un incidente: creación, cambios de estado, notas, avisos. |
| **Post-mortem** | El análisis escrito de un incidente resuelto: resumen, causa raíz, impacto, acciones. |

## Ciclo de vida del incidente

```
            ┌──────────────────────────────────────┐
            ▼                                      │
   open ──► investigating ──► mitigated ──► resolved
     │            ▲               │
     │            └───────────────┘
     └────────────────────────────────────────► resolved
```

| Desde | Puede pasar a |
|---|---|
| `open` | `investigating`, `resolved` |
| `investigating` | `mitigated`, `resolved` |
| `mitigated` | `investigating`, `resolved` |
| `resolved` | `investigating` (reapertura) |

Un incidente se puede resolver directamente desde `open` cuando resulta ser una falsa alarma. Un
incidente mitigado vuelve a `investigating` si la mitigación no aguanta. Uno resuelto se reabre
volviendo a `investigating`.

## Reglas

Estas reglas son el contrato del dominio. Si el código no las cumple, el defecto está en el código.

1. Todo incidente nace en `open`, con `started_at` y una entrada en la bitácora.
2. Solo se permiten las transiciones de la tabla anterior. Pedir una transición al mismo estado o a
   uno que no está en la tabla responde `409`.
3. Un incidente tiene `resolved_at` si y solo si su estado es `resolved`. Al reabrirlo, se borra.
4. `resolved_at` nunca es anterior a `started_at`.
5. Cada cambio de estado deja una entrada en la bitácora; la bitácora nunca se edita ni se borra.
6. Solo se escribe un post-mortem para un incidente resuelto, y cada incidente tiene a lo más uno.
7. En un mismo día, cada servicio tiene a lo más un turno de guardia vigente.
8. Un turno cubre desde `start_date` hasta `end_date`, ambos días incluidos, y `end_date` no es
   anterior a `start_date`.
9. Al abrir un incidente se avisa a quien está de guardia ese día en el servicio afectado. Si no
   hay nadie, el incidente se abre igual y la bitácora lo registra.
