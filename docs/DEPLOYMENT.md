# Deployment Notes

The server currently runs the MVP as a root user systemd service:

```bash
systemctl --user status local-ragbot.service
systemctl --user restart local-ragbot.service
systemctl --user stop local-ragbot.service
```

Local URL:

```text
http://127.0.0.1:8088
```

Rebuild the local index after changing files in `data/`:

```bash
cd /root/local-ragbot
python3 -m local_ragbot ingest data --dataset default --index-dir indexes
python3 -m local_ragbot ingest data --dataset coach-potato --index-dir indexes
systemctl --user restart local-ragbot.service
```

The service file lives at:

```text
/root/.config/systemd/user/local-ragbot.service
```
