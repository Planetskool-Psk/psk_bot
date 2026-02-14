# PSK Bot — Server Deployment Guide

Optimized for **2-core / 12GB RAM / AMD Milan VM** (Ubuntu/Debian).  
Domain: **chatbot.planetskool.com**

---

## Quick Deploy (One Command)

```bash
# 1. Clone the project onto your server
git clone <your-repo-url> /opt/psk-bot
cd /opt/psk-bot

# 2. Run the setup script
sudo bash setup_server.sh --email your@email.com
```

The script handles everything: system deps, swap, Ollama (gemma3:1b + embeddings), Python venv, `.env` generation with a secure API key, systemd services, Nginx reverse proxy with SSL (certbot), firewall, and log rotation.

### Setup Options

| Flag | Default | Description |
|------|---------|-------------|
| `--domain DOMAIN` | `chatbot.planetskool.com` | Nginx server name |
| `--email EMAIL` | *(none)* | Let's Encrypt notification email |
| `--app-dir PATH` | `/opt/psk-bot` | Install directory |
| `--port PORT` | `5173` | App listen port |
| `--git-repo URL` | *(none)* | Clone from this Git URL |
| `--skip-ssl` | `false` | Skip SSL setup (HTTP only) |
| `--skip-firewall` | `false` | Skip UFW configuration |

### Example: Deploy with git clone + SSL

```bash
sudo bash setup_server.sh \
  --git-repo https://github.com/youruser/psk-bot.git \
  --email admin@planetskool.com \
  --domain chatbot.planetskool.com
```

### Example: HTTP-only (no domain yet)

```bash
sudo bash setup_server.sh --skip-ssl --skip-firewall
```

---

## Architecture

```
Robot/Client ─▶ Nginx :443 (SSL) ─▶ PSK Bot :5173 ─▶ Ollama :11434 (gemma3:1b)
                                          │
                                     FAISS + Web Search
```

**Memory budget (12GB):** OS ~2GB, Ollama ~3-4GB, PSK Bot+embeddings ~4-5GB, FAISS ~1GB, headroom ~1GB.

---

## Robot API Reference

All endpoints under `/api/v1/`. Auth via `X-API-Key` header (set `PSK_API_KEY` in `.env`).

Full interactive docs at: `https://chatbot.planetskool.com/docs/`

### POST `/api/v1/chat`
```bash
curl -X POST https://chatbot.planetskool.com/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"message": "What is the leave policy?", "document_id": "abc123", "session_id": "robot_01"}'
```
Response: `{"response": "...", "latency_ms": 2340, "source": "document", "session_id": "robot_01"}`

### POST `/api/v1/chat/stream` — SSE streaming
Same body. Returns `data: {"token": "...", "type": "token"}` events, ending with `data: {"type": "done", ...}`.

### GET `/api/v1/health`
### GET `/api/v1/documents`

---

## Service Management

```bash
sudo systemctl start|stop|restart psk-bot
journalctl -u psk-bot -f                    # live logs
sudo systemctl status psk-bot ollama nginx   # check all services
```

## Nginx Management

```bash
sudo nginx -t                    # test config
sudo systemctl reload nginx      # apply changes
sudo tail -f /var/log/nginx/error.log
```

## SSL Certificate

```bash
# If skipped during setup, run manually:
sudo certbot --nginx -d chatbot.planetskool.com

# Check renewal
sudo certbot renew --dry-run
```

## Performance Tuning

If slow: reduce `LLM_NUM_CTX=1024`, `LLM_NUM_PREDICT=256`, or set `WEB_SEARCH_ENABLED=false` in `.env`.  
If OOM: reduce `CONTEXT_DOCUMENTS=3`, `MAX_CONVERSATION_HISTORY=4`.
