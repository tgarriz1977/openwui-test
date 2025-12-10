# Makefile para RAG Stack Kubernetes

# Variables
NAMESPACE = rag-system
REGISTRY = registry.arba.gov.ar/infraestructura
IMAGE_NAME = llamaindex-rag-api
VERSION = 1.0.0

.PHONY: help
help: ## Mostrar ayuda
	@echo "RAG Stack - Comandos disponibles:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# Docker
.PHONY: build
build: ## Construir imagen Docker
	cd docker && ./build-image.sh $(VERSION) $(REGISTRY)

.PHONY: build-local
build-local: ## Construir imagen localmente sin push
	cd docker && docker build -t $(IMAGE_NAME):$(VERSION) .

.PHONY: test-image
test-image: ## Testear imagen localmente
	docker run -d -p 8000:8000 --name test-llamaindex \
		-e LLM_PRIMARY_URL="http://test" \
		-e LLM_PRIMARY_MODEL="test" \
		-e EMBEDDING_URL="http://test" \
		-e EMBEDDING_MODEL="test" \
		-e RERANKER_URL="http://test" \
		-e RERANKER_MODEL="test" \
		-e QDRANT_HOST="localhost" \
		$(IMAGE_NAME):$(VERSION)
	@echo "Esperando 5 segundos..."
	@sleep 5
	@curl http://localhost:8000/health || true
	@docker stop test-llamaindex
	@docker rm test-llamaindex

.PHONY: pre-check
pre-check: ## Validar requisitos antes de desplegar
	./pre-deploy-check.sh

# Kubernetes
.PHONY: deploy
deploy: ## Desplegar stack completo
	./deploy.sh

.PHONY: deploy-custom
deploy-custom: ## Desplegar usando imagen custom
	kubectl apply -f 00-namespace.yaml
	kubectl apply -f 01-storage.yaml
	kubectl apply -f 02-qdrant.yaml
	kubectl apply -f 03-llamaindex-api-custom-image.yaml
	kubectl apply -f 04-openwebui.yaml
	kubectl apply -f 05-hpa.yaml

.PHONY: undeploy
undeploy: ## Eliminar deployment (mantener PVCs)
	kubectl delete -f 05-hpa.yaml || true
	kubectl delete -f 04-openwebui.yaml || true
	kubectl delete -f 03-llamaindex-api-custom-image.yaml || true
	kubectl delete -f 02-qdrant.yaml || true
	@echo "PVCs mantenidos. Para eliminar: make clean-data"

.PHONY: delete-all
delete-all: ## Eliminar TODO incluyendo datos
	kubectl delete namespace $(NAMESPACE) --wait=true

.PHONY: clean-data
clean-data: ## Eliminar solo PVCs
	kubectl delete -f 01-storage.yaml

# Gestión
.PHONY: status
status: ## Ver estado de los pods
	kubectl get all -n $(NAMESPACE)

.PHONY: logs
logs: ## Ver logs de LlamaIndex API
	kubectl logs -f -l app=llamaindex-api -n $(NAMESPACE)

.PHONY: logs-openwebui
logs-openwebui: ## Ver logs de Open WebUI
	kubectl logs -f -l app=open-webui -n $(NAMESPACE)

.PHONY: logs-qdrant
logs-qdrant: ## Ver logs de Qdrant
	kubectl logs -f -l app=qdrant -n $(NAMESPACE)

.PHONY: describe
describe: ## Describir recursos del namespace
	kubectl describe all -n $(NAMESPACE)

# Port forwarding
.PHONY: port-forward-api
port-forward-api: ## Port-forward LlamaIndex API (8000)
	kubectl port-forward -n $(NAMESPACE) svc/llamaindex-api-service 8000:8000

.PHONY: port-forward-webui
port-forward-webui: ## Port-forward Open WebUI (8080)
	kubectl port-forward -n $(NAMESPACE) svc/open-webui-service 8080:80

.PHONY: port-forward-qdrant
port-forward-qdrant: ## Port-forward Qdrant (6333)
	kubectl port-forward -n $(NAMESPACE) svc/qdrant-service 6333:6333

# Testing
.PHONY: test
test: ## Ejecutar tests del stack
	./test-stack.sh

.PHONY: test-api
test-api: ## Testear API con curl
	@echo "Testing health endpoint..."
	@kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n $(NAMESPACE) -- \
		curl -s http://llamaindex-api-service:8000/health | head -20

.PHONY: test-collections
test-collections: ## Listar colecciones
	@kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n $(NAMESPACE) -- \
		curl -s http://llamaindex-api-service:8000/collections

# Ingesta
.PHONY: ingest
ingest: ## Ingestar documentos (uso: make ingest PATH=/path/to/docs)
	./ingest-docs.sh $(PATH)

# Scaling
.PHONY: scale-api
scale-api: ## Escalar LlamaIndex API (uso: make scale-api REPLICAS=3)
	kubectl scale deployment llamaindex-api -n $(NAMESPACE) --replicas=$(REPLICAS)

.PHONY: scale-webui
scale-webui: ## Escalar Open WebUI (uso: make scale-webui REPLICAS=2)
	kubectl scale deployment open-webui -n $(NAMESPACE) --replicas=$(REPLICAS)

# Restart
.PHONY: restart-api
restart-api: ## Reiniciar LlamaIndex API
	kubectl rollout restart deployment/llamaindex-api -n $(NAMESPACE)

.PHONY: restart-webui
restart-webui: ## Reiniciar Open WebUI
	kubectl rollout restart deployment/open-webui -n $(NAMESPACE)

.PHONY: restart-all
restart-all: ## Reiniciar todos los deployments
	kubectl rollout restart deployment -n $(NAMESPACE)

# Update
.PHONY: update-config
update-config: ## Actualizar ConfigMap
	kubectl apply -f 00-namespace.yaml
	make restart-api

.PHONY: update-image
update-image: ## Actualizar imagen (después de build)
	kubectl set image deployment/llamaindex-api \
		llamaindex-api=$(REGISTRY)/$(IMAGE_NAME):$(VERSION) \
		-n $(NAMESPACE)

# Debug
.PHONY: shell-api
shell-api: ## Abrir shell en pod de API
	kubectl exec -it -n $(NAMESPACE) deployment/llamaindex-api -- /bin/bash

.PHONY: shell-qdrant
shell-qdrant: ## Abrir shell en pod de Qdrant
	kubectl exec -it -n $(NAMESPACE) deployment/qdrant -- /bin/sh

.PHONY: events
events: ## Ver eventos del namespace
	kubectl get events -n $(NAMESPACE) --sort-by='.lastTimestamp'

# Backup
.PHONY: backup-qdrant
backup-qdrant: ## Backup de Qdrant
	@echo "Creando backup de Qdrant..."
	kubectl exec -n $(NAMESPACE) deployment/qdrant -- \
		tar czf /tmp/qdrant-backup.tar.gz /qdrant/storage
	kubectl cp $(NAMESPACE)/$$(kubectl get pod -n $(NAMESPACE) -l app=qdrant -o jsonpath='{.items[0].metadata.name}'):/tmp/qdrant-backup.tar.gz \
		./backups/qdrant-backup-$$(date +%Y%m%d-%H%M%S).tar.gz

# Monitoring
.PHONY: top
top: ## Ver uso de recursos
	kubectl top pods -n $(NAMESPACE)

.PHONY: watch
watch: ## Watch pods status
	watch kubectl get pods -n $(NAMESPACE)

# Clean
.PHONY: clean-images
clean-images: ## Limpiar imágenes Docker locales
	docker rmi $(IMAGE_NAME):$(VERSION) || true
	docker rmi $(REGISTRY)/$(IMAGE_NAME):$(VERSION) || true
	docker rmi $(REGISTRY)/$(IMAGE_NAME):latest || true
