# Deploying coach-potato-app on a Raspberry Pi Kubernetes Cluster

## Overview

This guide covers:
1. Standing up a 3-node Pi cluster with K3s
2. Deploying coach-potato-app via the existing Kustomize overlays
3. LLM integration architecture — the right approach for the Pi's constraints

The existing repo already has `deploy/k8s/overlays/` — this guide wires your Pi cluster into that structure with a new `pi-cluster` overlay alongside `production`, `demo`, and `vps-test`.

---

## LLM Architecture Decision

> **tl;dr: Don't run LLMs on the Pi cluster. Run a dedicated inference server elsewhere and have coach-potato-app call its API.**

### Why not on the Pi?

Pis have no GPU. Every token is generated on CPU + RAM, which means:

- Mistral 7B Q4 on a Pi 5 8GB: ~3–6 tok/s — usable for async/background tasks, painful for interactive chat
- Any model >7B parameters: effectively unusable
- LLM inference doesn't distribute across cluster nodes — it can't be spread across pi-1/pi-2/pi-3 to go faster

The Pi cluster is well-suited for **running the app and its database**. It is the wrong tool for inference.

### The better architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│      Pi Cluster (LAN)       │        │   Inference Server           │
│                             │        │   (wherever it lives)        │
│  ┌─────────────────────┐   │  HTTP  │                              │
│  │  coach-potato-app   │───┼────────▶  Ollama / vLLM / llama.cpp  │
│  └─────────────────────┘   │        │  OpenAI-compatible API       │
│  ┌─────────────────────┐   │        │                              │
│  │  postgres           │   │        │  Models: Mistral, Llama,     │
│  └─────────────────────┘   │        │  Qwen, Gemma, ...            │
└─────────────────────────────┘        └──────────────────────────────┘
```

coach-potato-app talks to the inference server over HTTP — the same way it would talk to OpenAI or Anthropic. The cluster doesn't need to know or care what model is running or where.

### Inference server options (not built here, just choose one)

| Option | Where | Best for |
|---|---|---|
| **Old desktop/laptop with GPU** | Home LAN | Private, fast, free after hardware |
| **STRATO VPS + Ollama** | Cloud | Always-on, reachable from anywhere |
| **Hetzner dedicated GPU server** | Cloud | Serious throughput, €/hr billing |
| **RunPod / vast.ai** | Cloud | On-demand, cheap for sporadic use |
| **OpenAI / Anthropic / Groq API** | SaaS | Zero setup, pay per token |

All of these expose an OpenAI-compatible `/v1/chat/completions` endpoint (Ollama does natively, others via config). coach-potato-app only needs one env var pointing at the right base URL.

### What this means for configuration

When LLM integration is built, coach-potato-app will need two env vars:

```bash
LLM_BASE_URL=http://your-inference-server:11434/v1   # or https://api.openai.com/v1
LLM_API_KEY=your-key-if-needed                        # empty string for local Ollama
```

These go into a Kubernetes Secret and get injected into the deployment — the overlay structure already supports this pattern. **No changes to the Pi cluster setup are needed when you add LLM support later.**

---

## 1. Pi Cluster Prerequisites

### Hardware assumptions

| Role | Node | Recommended |
|---|---|---|
| control-plane | pi-1 | Pi 4/5 8GB |
| worker | pi-2 | Pi 4/5 4–8GB |
| worker | pi-3 | Pi 4/5 4–8GB |

All three wired via Ethernet to your switch. Wi-Fi is not recommended for cluster traffic.

### OS prep (all 3 nodes)

Use **Raspberry Pi OS Lite 64-bit** (bookworm). After flashing:

```bash
# Disable swap — required for Kubernetes
sudo dsystemctl disable dphys-swapfile
sudo swapoff -a

# Enable cgroups for container resource limits
# Edit /boot/firmware/cmdline.txt, append to the single line:
sudo sed -i '$ s/$/ cgroup_enable=cpuset cgroup_enable=memory cgroup_memory=1/' /boot/firmware/cmdline.txt

sudo reboot
```

Set static IPs or reserve DHCP leases for all three nodes. Example `/etc/hosts` on each node:

```
192.168.1.101  pi-1
192.168.1.102  pi-2
192.168.1.103  pi-3
```

---

## 2. Install K3s

K3s is the right Kubernetes distribution for Pi — it's a single binary, ARM64-native, and ships with Traefik as ingress and local-path-provisioner for storage.

### Control plane (pi-1)

```bash
curl -sfL https://get.k3s.io | sh -s - \
  --write-kubeconfig-mode 644 \
  --disable traefik \        # we'll use our own ingress-nginx
  --node-name pi-1
```

Grab the join token:

```bash
sudo cat /var/lib/rancher/k3s/server/node-token
```

### Workers (pi-2, pi-3)

```bash
curl -sfL https://get.k3s.io | K3S_URL=https://192.168.1.101:6443 \
  K3S_TOKEN=<token-from-above> sh -s - \
  --node-name pi-2   # pi-3 on the third node
```

### Verify from pi-1

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl get nodes
# NAME   STATUS   ROLES                  AGE
# pi-1   Ready    control-plane,master   2m
# pi-2   Ready    <none>                 1m
# pi-3   Ready    <none>                 1m
```

Copy kubeconfig to your dev machine:

```bash
scp pi@pi-1:/etc/rancher/k3s/k3s.yaml ~/.kube/pi-cluster.yaml
# Replace 127.0.0.1 with pi-1's actual IP
sed -i 's/127.0.0.1/192.168.1.101/' ~/.kube/pi-cluster.yaml
```

---

## 3. Cluster Infrastructure

### Ingress

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/baremetal/deploy.yaml
```

Since this is bare-metal (no cloud LoadBalancer), patch it to use a NodePort or hostNetwork. Simplest option — use a NodePort and point your router/DNS to any Pi's IP on that port.

### GHCR Image Pull Secret

Your images are private on `ghcr.io`. Every namespace that pulls them needs this secret:

```bash
kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=ffworker \
  --docker-password=<your-PAT-with-read:packages> \
  --namespace=coach-potato
```

Or put it in your Kustomize base so it's managed as code (see section 4).

### Storage

K3s ships with `local-path-provisioner` — this is fine for Postgres on a Pi cluster. Data lives on whichever node the pod schedules to, so add a node affinity to pin Postgres to one node to avoid data loss on rescheduling:

```yaml
# In your postgres StatefulSet
nodeAffinity:
  required:
    nodeSelectorTerms:
      - matchExpressions:
          - key: kubernetes.io/hostname
            operator: In
            values: [pi-1]  # or whichever node
```

---

## 4. New Kustomize Overlay: pi-cluster

Create `deploy/k8s/overlays/pi-cluster/` alongside your existing overlays.

### Directory structure

```
deploy/k8s/overlays/pi-cluster/
├── kustomization.yaml
├── ingress-patch.yaml
├── resources-patch.yaml
└── postgres-affinity-patch.yaml
```

### kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base

namePrefix: ""
namespace: coach-potato

images:
  - name: ghcr.io/ffworker/coach-potato-app
    newTag: latest  # CI will overwrite this with the commit SHA

patches:
  - path: ingress-patch.yaml
  - path: resources-patch.yaml
  - path: postgres-affinity-patch.yaml

secretGenerator:
  - name: ghcr-pull-secret
    type: kubernetes.io/dockerconfigjson
    files:
      - .dockerconfigjson  # gitignored, populated in cluster bootstrap
```

### ingress-patch.yaml

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: coach-potato
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
spec:
  ingressClassName: nginx
  rules:
    - host: coach.local     # or your LAN hostname / Tailscale domain
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: coach-potato
                port:
                  number: 3000
```

### resources-patch.yaml

Pi has limited RAM — be conservative:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: coach-potato
spec:
  replicas: 1          # scale to 2 on pi-2/pi-3 if needed
  template:
    spec:
      containers:
        - name: coach-potato
          resources:
            requests:
              memory: 256Mi
              cpu: 250m
            limits:
              memory: 512Mi
              cpu: 1000m
```

### postgres-affinity-patch.yaml

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          required:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: kubernetes.io/hostname
                    operator: In
                    values: [pi-1]
```

---

## 5. Deploy Manually (First Time)

```bash
export KUBECONFIG=~/.kube/pi-cluster.yaml

# Create namespace
kubectl create namespace coach-potato

# Apply the overlay
kubectl apply -k deploy/k8s/overlays/pi-cluster/

# Watch rollout
kubectl rollout status deployment/coach-potato -n coach-potato

# Check pods
kubectl get pods -n coach-potato
```

---

## 6. Wire it into the CI/CD Pipeline

### Add the new overlay to the CI workflow

In your CI workflow, add the pi-cluster manifest render:

```yaml
- run: kubectl kustomize deploy/k8s/overlays/pi-cluster > /tmp/coach-potato-pi.yaml
```

### Add it to Publish Images

In the "Update immutable environment tags" step, add:

```bash
cd ../pi-cluster
kustomize edit set image ghcr.io/ffworker/coach-potato-app=ghcr.io/ffworker/coach-potato-app:${GITHUB_SHA}
```

And include the file in the git commit:

```bash
git add deploy/k8s/overlays/pi-cluster/kustomization.yaml
```

### Optional: Add a Deploy Pi job

If you want automated push-to-Pi deploys (similar to Deploy Alpha), you need your Pi cluster's kubeconfig as a secret, then:

```yaml
- name: Deploy to Pi cluster
  env:
    KUBECONFIG_DATA: ${{ secrets.PI_CLUSTER_KUBECONFIG }}
  run: |
    echo "$KUBECONFIG_DATA" | base64 -d > /tmp/pi.yaml
    kubectl --kubeconfig=/tmp/pi.yaml apply -k deploy/k8s/overlays/pi-cluster/
    kubectl --kubeconfig=/tmp/pi.yaml rollout status deployment/coach-potato -n coach-potato
```

---

## 7. LLM Integration (Future)

> LLM support is **not built here**. See the "LLM Architecture Decision" section at the top. This section documents what the integration will look like when you build it, so the overlay structure is designed to support it from day one.

### How it will plug in

When coach-potato-app gains LLM support, it will read the inference endpoint from env vars. These go into a Kubernetes Secret in the overlay — nothing else in the cluster needs to change.

Add to `deploy/k8s/overlays/pi-cluster/kustomization.yaml`:

```yaml
secretGenerator:
  - name: llm-config
    literals:
      - LLM_BASE_URL=http://your-inference-server:11434/v1
      - LLM_API_KEY=     # empty for unauthenticated local Ollama
```

And a patch to mount it into the deployment:

```yaml
# llm-env-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: coach-potato
spec:
  template:
    spec:
      containers:
        - name: coach-potato
          envFrom:
            - secretRef:
                name: llm-config
```

That's the entire cluster-side change. The inference server itself lives elsewhere — on your home network, your STRATO VPS, or a cloud GPU provider — and the Pi cluster just calls its API over HTTP.

### If your inference server is on your LAN

coach-potato-app running in the Pi cluster can reach any LAN host directly:

```bash
LLM_BASE_URL=http://192.168.1.50:11434/v1   # e.g. a desktop with a GPU running Ollama
```

No VPN or tunnel needed if both the cluster and the inference server are on the same network.

### If your inference server is remote (VPS/cloud)

Use Tailscale to connect the Pi cluster and the inference server on a private overlay network — then the URL stays stable regardless of where either machine is:

```bash
LLM_BASE_URL=http://inference-server.your-tailnet.ts.net:11434/v1
```

---

## 8. Accessing the App

### Option A: Local LAN only
Point your browser at `http://<any-pi-ip>:<nodeport>` — get the NodePort with:
```bash
kubectl get svc -n ingress-nginx
```

### Option B: Tailscale (recommended for remote access)
Install Tailscale on pi-1 and expose the cluster via `tailscale serve`. Clean, no port-forwarding required, works over the internet.

### Option C: DNS on your router
Point `coach.local` (or a real domain) to pi-1's LAN IP via your router's DNS.

---

## Quick Reference

```bash
# Apply changes
kubectl apply -k deploy/k8s/overlays/pi-cluster/

# Check status
kubectl get pods,svc,ingress -n coach-potato

# Logs
kubectl logs -n coach-potato deploy/coach-potato -f

# Postgres shell
kubectl exec -n coach-potato statefulset/postgres -- psql -U postgres

# Rollback
kubectl rollout undo deployment/coach-potato -n coach-potato
```
