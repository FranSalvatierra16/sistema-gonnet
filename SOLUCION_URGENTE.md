# 🚨 SOLUCIÓN URGENTE: Eliminar límites de BD

## ⚡ OPCIÓN 1: PlanetScale (RECOMENDADO)

### Ventajas
- ✅ **SIN límites** de conexiones
- ✅ **SIN límites** de queries por hora
- ✅ **GRATIS** hasta 5GB y 1 billón de lecturas/mes
- ✅ Compatible con MySQL (tu app actual)
- ✅ Escalable automáticamente
- ⏱️ **Tiempo: 30-40 minutos**

### Costo
- **Gratis**: 0-5GB, 1 billón lecturas/mes
- **Scaler**: $29/mes (10GB, sin límites)
- vs JawsDB Leopard actual: $35/mes (CON límites)

### Pasos de migración

#### 1. Crear cuenta en PlanetScale
```bash
# Ir a: https://planetscale.com
# Crear cuenta gratis
# Crear nueva base de datos: "gonnet-sistema"
```

#### 2. Hacer backup de datos actuales
```bash
# Desde tu máquina local
heroku run bash --app gonnet-interno

# Dentro del dyno:
mysqldump -h tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com \
  -u oaai2ab9qsc7xvyn \
  -pit2cxhq71iiubhlj \
  vgd8ktskappw7cmj > backup.sql

# Guardar backup localmente
exit
heroku run cat backup.sql --app gonnet-interno > backup_$(date +%Y%m%d).sql
```

#### 3. Importar datos a PlanetScale
```bash
# Desde PlanetScale dashboard:
# 1. Ir a "Imports"
# 2. Subir backup.sql
# 3. Esperar importación (5-10 minutos)

# O vía CLI:
pscale import gonnet-sistema main backup.sql
```

#### 4. Obtener nueva connection string
```bash
# En PlanetScale dashboard:
# - Ir a "Connect"
# - Seleccionar "Django"
# - Copiar DATABASE_URL
```

#### 5. Actualizar Heroku
```bash
heroku config:set DATABASE_URL="mysql://[usuario]:[password]@[host]/[database]?ssl-mode=REQUIRED" --app gonnet-interno

# Reiniciar app
heroku restart --app gonnet-interno
```

#### 6. Verificar funcionamiento
```bash
# Probar login
curl -I https://gonnet-interno-052a6cec3da9.herokuapp.com/login/

# Debería responder 200 OK sin errores de conexión
```

---

## ⚡ OPCIÓN 2: Railway PostgreSQL (Alternativa)

### Ventajas
- ✅ **SIN límites** de conexiones
- ✅ **SIN límites** de queries
- ✅ $5/mes todo incluido
- ✅ Requiere pequeños cambios en models (MySQL → PostgreSQL)
- ⏱️ **Tiempo: 1-2 horas** (incluye cambios de código)

### Pasos

#### 1. Crear proyecto en Railway
```bash
# Ir a: https://railway.app
# Login con GitHub
# "New Project" → "Provision PostgreSQL"
```

#### 2. Exportar datos de MySQL
```bash
heroku run python manage.py dumpdata --natural-foreign --natural-primary > backup.json --app gonnet-interno
```

#### 3. Actualizar requirements.txt
```python
# Cambiar:
mysqlclient==2.2.0
# Por:
psycopg2-binary==2.9.10
```

#### 4. Actualizar settings.py
```python
# Cambiar ENGINE de MySQL a PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        # ... resto igual
    }
}
```

#### 5. Migrar y cargar datos
```bash
# En Railway:
python manage.py migrate
python manage.py loaddata backup.json
```

---

## ⚡ OPCIÓN 3: Migrar TODO a Railway (Completa)

### Ventajas
- ✅ **SIN límites** de nada
- ✅ **$5/mes total** (vs $60/mes actual)
- ✅ Mejor rendimiento
- ✅ Más fácil de mantener
- ⏱️ **Tiempo: 1 hora**

### Pasos

#### 1. Crear proyecto en Railway
```bash
# Ir a: https://railway.app
# "New Project" → "Deploy from GitHub"
# Seleccionar repo "sistema-gonnet"
```

#### 2. Agregar PostgreSQL
```bash
# En Railway project:
# "New" → "Database" → "PostgreSQL"
```

#### 3. Configurar variables de entorno
```bash
# Copiar TODAS de Heroku:
heroku config --app gonnet-interno

# Pegar en Railway → Settings → Variables
# Actualizar DATABASE_URL con la de Railway
```

#### 4. Deploy automático
```bash
# Railway detecta Django y hace deploy automáticamente
# URL: https://[tu-proyecto].up.railway.app
```

#### 5. Migrar datos
```bash
# Opción A: dumpdata/loaddata
railway run python manage.py loaddata backup.json

# Opción B: mysqldump → PostgreSQL (más complejo)
```

---

## 📊 COMPARACIÓN DE OPCIONES

| Opción | Tiempo | Costo/mes | Dificultad | Límites | Recomendado |
|--------|--------|-----------|------------|---------|-------------|
| **PlanetScale** | 30 min | $0-29 | ⭐ Fácil | ✅ SIN límites | ✅ **SÍ** |
| **Railway PG** | 1 h | $5 | ⭐⭐ Medio | ✅ SIN límites | ✅ Sí |
| **Railway TODO** | 1 h | $5 | ⭐⭐ Medio | ✅ SIN límites | ✅ Sí |
| **JawsDB Kitefin** | - | $50 | ❌ No funciona | ⚠️ Límites mayores | ❌ No |
| **Esperar reset** | 0 min | $35 | ⭐ Fácil | ❌ **PROBLEMA SE REPITE** | ❌ **NO** |

---

## 🎯 MI RECOMENDACIÓN FINAL

### Para resolver AHORA y definitivamente:

**1️⃣ PlanetScale (30 minutos)**
- Mantener todo igual
- Solo cambiar base de datos
- Sin límites
- Gratis o $29/mes (vs $35/mes JawsDB)

**2️⃣ Railway completo (1 hora)**
- Mejor solución a largo plazo
- $5/mes total (ahorro de $55/mes)
- Sin límites
- Mejor rendimiento

---

## ⚠️ LO QUE NO DEBES HACER

❌ Quedarte con JawsDB Leopard
- Los errores van a volver
- Pierdes tiempo cada vez que pasa
- Mala experiencia para usuarios

❌ Esperar a que "se arregle solo"
- El límite de 18,000 queries/hora es MUY bajo
- Con 3-4 usuarios simultáneos ya lo alcanzas

❌ Upgrade a JawsDB Kitefin
- Ya probamos, tiene problemas de migración
- Sigue teniendo límites

---

## 🚀 ¿Empezamos?

Te recomiendo **PlanetScale** porque:
1. ✅ Más rápido (30 min)
2. ✅ No cambia nada de tu código
3. ✅ Sin límites garantizado
4. ✅ Puedes probar gratis

**¿Quieres que te ayude con la migración a PlanetScale AHORA?**

Solo necesito que:
1. Crees cuenta en https://planetscale.com
2. Crees una base de datos nueva
3. Me des la connection string

Y yo hago todo lo demás (backup, migración, configuración).

