# Bot de Ejecuciones RPA - Cinemex

Bot de Telegram que permite a usuarios autorizados disparar procesos UiPath RPA desde su celular. Los procesos se encolan y ejecutan de forma secuencial a través de `UiRobot.exe`.

## Arquitectura

```
Telegram (usuario)
       │
       ▼
python-telegram-bot  ←  message_handler.py
       │
       ├── SessionService   (verificación de teléfono, estado de conversación)
       ├── RpaRepository    (escanea carpeta de .nupkg)
       └── RpaService       (cola asyncio → UiRobot.exe)
```

## Requisitos previos

| Requisito | Versión mínima |
|-----------|---------------|
| Windows | 10 / Server 2016 |
| Python | 3.11+ |
| UiPath Studio o UiPath Robot | Cualquier versión con `UiRobot.exe` |
| Acceso a Internet | Para la API de Telegram |

---

## 1. Crear el bot de Telegram

1. Abre Telegram y busca **@BotFather**.
2. Ejecuta `/newbot` y sigue las instrucciones.
3. Guarda el **token** que BotFather te entrega (formato `123456789:AAF...`).

Para obtener los chat IDs de soporte (opcional):
- Añade **@userinfobot** a un grupo o envíale un mensaje directo; te devolverá el chat ID.

---

## 2. Entorno Python

```powershell
# Crear entorno virtual
python -m venv .venv

# Activar entorno
.\.venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt
```

> Si PowerShell bloquea la ejecución de scripts, ejecuta primero:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

## 3. Configuración del archivo `.env`

Copia la plantilla y edítala con los valores del entorno productivo:

```powershell
Copy-Item .env.example .env
notepad .env
```

Si no existe `.env.example`, crea `.env` con el siguiente contenido:

```dotenv
# --- Telegram ---
BOT_TOKEN=123456789:AAF_TU_TOKEN_AQUI

# Números autorizados separados por comas (con código de país).
# Dejar vacío para acceso abierto (sin verificación de teléfono).
ALLOWED_PHONES=+521234567890,+529876543210

# --- UiPath ---
UIROBOT_EXE=C:\Program Files\UiPath\Studio\UiRobot.exe
RPA_FOLDER=C:\RPAs
# Argumentos que van entre UiRobot.exe y la ruta del .nupkg
UIROBOT_ARGS=execute --file

# --- Cola ---
MAX_QUEUE_SIZE=10

# --- Búsqueda fuzzy ---
# Umbral de similitud 0-100. 70 = mínimo 70% de coincidencia
FUZZY_THRESHOLD=70

# --- Palabras clave que muestran el menú ---
MENU_KEYWORDS=menu,menú,bots,robots,procesos,lista,inicio,ayuda,help

# --- Logging ---
LOG_LEVEL=INFO
LOG_FILE=logs/bot.txt
LOG_MAX_BYTES=5242880
LOG_BACKUP_COUNT=3

# --- Soporte (chat IDs separados por comas, dejar vacío para desactivar) ---
SUPPORT_CHAT_IDS=
```

### Variables obligatorias

| Variable | Descripción |
|----------|-------------|
| `BOT_TOKEN` | Token del bot obtenido de BotFather |
| `UIROBOT_EXE` | Ruta absoluta a `UiRobot.exe` |
| `RPA_FOLDER` | Carpeta que contiene los paquetes `.nupkg` |

### Variables opcionales

| Variable | Default | Descripción |
|----------|---------|-------------|
| `ALLOWED_PHONES` | *(vacío)* | Sin valor = acceso abierto; con valor = solo esos números |
| `SUPPORT_CHAT_IDS` | *(vacío)* | IDs de Telegram a notificar cuando un proceso falla |
| `MAX_QUEUE_SIZE` | `10` | Máximo de procesos en cola simultáneos |
| `FUZZY_THRESHOLD` | `70` | Porcentaje mínimo de coincidencia para búsqueda por nombre |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## 4. Carpeta de paquetes RPA

La carpeta indicada en `RPA_FOLDER` debe contener los archivos `.nupkg` generados por UiPath Studio.

```
C:\RPAs\
    MiProceso.1.0.0.nupkg
    OtroProceso.2.1.3.nupkg
```

- Si existen múltiples versiones del mismo paquete, el bot carga automáticamente la más reciente (por fecha de modificación).
- El bot lee la carpeta cada vez que un usuario solicita el menú, por lo que agregar un nuevo `.nupkg` no requiere reiniciar el servicio.

---

## 5. Verificar la instalación manualmente

```powershell
cd C:\Bots\Bot_Ejecuciones_Cinemex
.\.venv\Scripts\Activate.ps1
python main.py
```

El bot debe imprimir en consola algo similar a:

```
2024-01-15 10:00:00 | INFO     | rpa_bot                     | Starting RPA Bot
2024-01-15 10:00:00 | INFO     | rpa_bot                     | RPA folder   : C:\RPAs
2024-01-15 10:00:00 | INFO     | rpa_bot                     | UiRobot path : C:\Program Files\UiPath\Studio\UiRobot.exe
...
2024-01-15 10:00:01 | INFO     | rpa_bot.handler             | Handlers registered
2024-01-15 10:00:01 | INFO     | rpa_bot                     | Bot is up and polling for messages
```

Prueba enviando `/start` al bot desde Telegram. Detén el proceso con `Ctrl+C` antes de continuar con el despliegue como servicio.

---

## 6. Despliegue como servicio de Windows (NSSM)

NSSM (Non-Sucking Service Manager) registra el bot como un servicio de Windows que inicia automáticamente con el sistema y se reinicia ante fallos.

### 6.1 Instalar NSSM

Descarga NSSM desde [nssm.cc](https://nssm.cc/download) y coloca `nssm.exe` en una carpeta del PATH, por ejemplo `C:\Tools\nssm\`.

### 6.2 Registrar el servicio

Abre PowerShell **como Administrador**:

```powershell
$nssm     = "C:\Tools\nssm\nssm.exe"
$svcName  = "BotEjecucionesCinemex"
$python   = "C:\Bots\Bot_Ejecuciones_Cinemex\.venv\Scripts\python.exe"
$script   = "C:\Bots\Bot_Ejecuciones_Cinemex\main.py"
$workDir  = "C:\Bots\Bot_Ejecuciones_Cinemex"

& $nssm install $svcName $python $script
& $nssm set $svcName AppDirectory $workDir
& $nssm set $svcName AppStdout "$workDir\logs\service_stdout.txt"
& $nssm set $svcName AppStderr "$workDir\logs\service_stderr.txt"
& $nssm set $svcName AppRotateFiles 1
& $nssm set $svcName AppRotateBytes 5242880
& $nssm set $svcName Start SERVICE_AUTO_START
& $nssm set $svcName ObjectName LocalSystem
```

### 6.3 Iniciar y verificar el servicio

```powershell
Start-Service $svcName
Get-Service  $svcName
```

Para consultar el estado en cualquier momento:

```powershell
Get-Service BotEjecucionesCinemex
```

### 6.4 Comandos de gestión

```powershell
# Detener
Stop-Service BotEjecucionesCinemex

# Reiniciar
Restart-Service BotEjecucionesCinemex

# Eliminar el servicio (detener primero)
Stop-Service BotEjecucionesCinemex
& "C:\Tools\nssm\nssm.exe" remove BotEjecucionesCinemex confirm
```

---

## 7. Alternativa: Tarea programada de Windows

Si no se puede instalar NSSM, usa el Programador de tareas:

```powershell
$action  = New-ScheduledTaskAction `
    -Execute "C:\Bots\Bot_Ejecuciones_Cinemex\.venv\Scripts\python.exe" `
    -Argument "C:\Bots\Bot_Ejecuciones_Cinemex\main.py" `
    -WorkingDirectory "C:\Bots\Bot_Ejecuciones_Cinemex"

$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName "BotEjecucionesCinemex" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force
```

Iniciar la tarea inmediatamente:

```powershell
Start-ScheduledTask -TaskName "BotEjecucionesCinemex"
```

---

## 8. Logs

Los logs rotativos se almacenan en la ruta definida en `LOG_FILE` (por defecto `logs/bot.txt`).

```
logs/
    bot.txt          ← log activo
    bot.txt.1        ← rotación anterior
    bot.txt.2
    bot.txt.3
```

Para seguir el log en tiempo real desde PowerShell:

```powershell
Get-Content "C:\Bots\Bot_Ejecuciones_Cinemex\logs\bot.txt" -Wait -Tail 50
```

---

## 9. Actualizar paquetes RPA

No se requiere reiniciar el bot. Solo copia el nuevo `.nupkg` a la carpeta `RPA_FOLDER`. El menú se actualiza en la siguiente solicitud del usuario.

---

## 10. Actualizar el bot

```powershell
cd C:\Bots\Bot_Ejecuciones_Cinemex

# Detener el servicio antes de actualizar
Stop-Service BotEjecucionesCinemex

git pull

.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Start-Service BotEjecucionesCinemex
```

---

## 11. Solución de problemas

| Síntoma | Causa probable | Solución |
|---------|---------------|----------|
| El bot no responde en Telegram | Token inválido o sin acceso a Internet | Verificar `BOT_TOKEN` y conectividad |
| `UiRobot.exe not found` | Ruta incorrecta | Ajustar `UIROBOT_EXE` en `.env` |
| El menú aparece vacío | Carpeta RPA vacía o ruta incorrecta | Verificar `RPA_FOLDER` y que contenga `.nupkg` |
| Usuario no puede ingresar | Teléfono no en lista | Agregar número a `ALLOWED_PHONES` o vaciar para acceso abierto |
| Cola llena | `MAX_QUEUE_SIZE` demasiado bajo o procesos muy largos | Aumentar `MAX_QUEUE_SIZE` o revisar duración de los RPAs |
| Servicio no inicia | Error en `.env` o Python no encontrado | Revisar `logs\service_stderr.txt` |

Para diagnóstico detallado, establece `LOG_LEVEL=DEBUG` en `.env` y reinicia el servicio.
