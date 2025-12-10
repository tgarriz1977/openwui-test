# Redis Stateless para Open WebUI

## Cambios Realizados

Se agregó un **Redis dedicado y stateless** para desacoplar las sesiones de los pods de Open WebUI, permitiendo una arquitectura completamente stateless.

## Archivos Modificados/Creados

1. **08-redis.yaml** (NUEVO)
   - Redis 7 Alpine (imagen ligera)
   - Configuración sin persistencia (stateless)
   - Límite de memoria: 512MB
   - Política de eviction: allkeys-lru

2. **03-secrets.yaml** (MODIFICADO)
   - Cambiado de Redis Sentinel del organismo al Redis dedicado
   - DB 0: Estado general y sesiones
   - DB 1: Coordinación de WebSockets

3. **kustomization.yaml** (MODIFICADO)
   - Agregado 08-redis.yaml a los recursos

## ¿Por qué Stateless?

### Función de Redis en Open WebUI

Redis hace que los pods de Open WebUI sean **completamente intercambiables**:

- **REDIS_URL** (DB 0): Estado de aplicación, sesiones, cache
- **WEBSOCKET_REDIS_URL** (DB 1): Coordinación de WebSockets entre réplicas

### Beneficios

1. **Pods Stateless**: Cualquier pod puede atender cualquier request
2. **No Sticky Sessions**: No se necesitan (aunque las que tienes en el Ingress son inofensivas)
3. **Escalado Horizontal**: Puedes aumentar réplicas sin problemas
4. **Resilencia**: Los pods pueden reiniciarse sin afectar a los usuarios
5. **JWT + Redis**: Las sesiones sobreviven a reinicios de pods

## Configuración de Redis

### Sin Persistencia (Stateless)

```yaml
args:
  - --save ""                      # Sin snapshots RDB
  - --appendonly no                # Sin AOF
  - --maxmemory 512mb              # Límite de memoria
  - --maxmemory-policy allkeys-lru # Evict automático
```

**¿Por qué sin persistencia?**

- Los datos en Redis son **temporales por naturaleza**:
  - Sesiones activas de WebSocket
  - Cache de queries
  - Estado temporal de la aplicación

- **La data persistente está en PostgreSQL** (desplegado internamente en 09-postgresql.yaml)

- Si Redis se reinicia:
  - Los usuarios deben refrescar la página
  - Las sesiones se recrean automáticamente
  - **No se pierde data importante** (está en PostgreSQL)

### Recursos Asignados

```yaml
requests:
  memory: "256Mi"
  cpu: "100m"
limits:
  memory: "512Mi"
  cpu: "500m"
```

**Justificación:**
- Suficiente para ~100-200 usuarios concurrentes
- Puedes aumentar si necesitas más

## Arquitectura Resultante

```
┌─────────────────────────────────────────┐
│         Nginx Ingress Controller         │
│    (con sticky sessions - opcional)      │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│        Open WebUI Service (ClusterIP)    │
└─────────────────┬───────────────────────┘
                  │
      ┌───────────┴───────────┐
      ▼                       ▼
┌──────────┐            ┌──────────┐
│ Pod 1    │            │ Pod 2    │  (Stateless)
│ OpenWebUI│            │ OpenWebUI│
└────┬─────┘            └────┬─────┘
     │                       │
     └───────────┬───────────┘
                 │
     ┌───────────┴───────────┐
     ▼                       ▼
┌──────────┐          ┌──────────┐
│ Redis    │          │PostgreSQL│
│ Stateless│          │ (Interno)│
│ (Sesiones│          │ (Data)   │
│  Cache)  │          │          │
└──────────┘          └──────────┘
```

## Variables de Entorno Relevantes

En [04-openwebui.yaml](04-openwebui.yaml):

```yaml
# PostgreSQL - Data persistente (interno)
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: postgresql-secret
      key: database-url  # postgresql://ragsystemuser:rag322wq@postgres:5432/ragsystemdb

# Redis - Sesiones y WebSockets (stateless)
- name: WEBSOCKET_MANAGER
  value: "redis"
- name: WEBSOCKET_REDIS_URL
  valueFrom:
    secretKeyRef:
      name: redis-config
      key: websocket-url  # redis://redis-service:6379/1
- name: REDIS_URL
  valueFrom:
    secretKeyRef:
      name: redis-config
      key: cache-url      # redis://redis-service:6379/0

# Secret compartida entre pods
- name: WEBUI_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: openwebui-secret
      key: secret-key
```

## Verificación Post-Despliegue

### 1. Verificar que Redis está corriendo

```bash
kubectl get pods -n rag-system | grep redis
kubectl logs -n rag-system -l app=redis
```

### 2. Verificar conectividad desde Open WebUI

```bash
kubectl exec -it -n rag-system deployment/open-webui -- sh
# Dentro del pod:
apk add redis
redis-cli -h redis-service ping
# Debe responder: PONG
```

### 3. Verificar que Open WebUI usa Redis

```bash
kubectl logs -n rag-system -l app=open-webui | grep -i redis
# Buscar: "Using Redis to manage websockets"
```

### 4. Test de escalado

```bash
# Escalar a 2 réplicas
kubectl scale deployment open-webui -n rag-system --replicas=2

# Verificar que ambas réplicas están healthy
kubectl get pods -n rag-system -l app=open-webui

# Probar en el navegador - las sesiones deben funcionar
```

## Troubleshooting

### Redis no inicia

```bash
kubectl describe pod -n rag-system -l app=redis
kubectl logs -n rag-system -l app=redis
```

### Open WebUI no se conecta a Redis

```bash
# Verificar secret
kubectl get secret redis-config -n rag-system -o yaml

# Verificar que el servicio resuelve
kubectl exec -it -n rag-system deployment/open-webui -- nslookup redis-service
```

### WebSockets no funcionan

Verificar en los logs de Open WebUI:
```bash
kubectl logs -n rag-system -l app=open-webui | grep -i websocket
```

Debe aparecer:
```
DEBUG:open_webui.socket.main:Using Redis to manage websockets
```

## Diferencias vs Redis Sentinel Anterior

| Aspecto | Redis Sentinel (Anterior) | Redis Dedicado (Nuevo) |
|---------|---------------------------|------------------------|
| **Ubicación** | Cluster compartido del organismo | Dedicado al namespace rag-system |
| **Persistencia** | Probablemente activa | Deshabilitada (stateless) |
| **Databases** | 2 y 3 (compartidas) | 0 y 1 (dedicadas) |
| **Control** | Gestionado por el organismo | Gestionado por ti |
| **HA** | Sentinel (alta disponibilidad) | Single instance |
| **Propósito** | Infraestructura general | Específico para Open WebUI |

## Consideraciones de Producción

### ¿Cuándo necesitas HA para Redis?

Si necesitas **alta disponibilidad** (que Redis sobreviva a caídas), considera:

1. **Redis Sentinel** (3 nodos)
2. **Redis Cluster** (si necesitas más de 512MB)
3. **Servicio gestionado** (si el organismo lo ofrece)

Para la mayoría de casos, **un Redis simple es suficiente** porque:
- Si Redis cae, los usuarios solo necesitan refrescar
- Los pods de Open WebUI se recuperan automáticamente
- La data importante está en PostgreSQL

### Monitoreo Recomendado

```yaml
# Agregar en 08-redis.yaml si tienes Prometheus
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "6379"
```

## Próximos Pasos

1. Aplicar el despliegue:
   ```bash
   kubectl apply -k .
   ```

2. Verificar que todo funciona (ver sección Verificación)

3. Escalar a múltiples réplicas cuando sea necesario:
   ```bash
   kubectl scale deployment open-webui -n rag-system --replicas=3
   ```

4. Opcional: Remover sticky sessions del Ingress (ya no son necesarias)
