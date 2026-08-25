# CI, Docker und Deployment

## Workflows

- `.github/workflows/ci.yml` installiert die Abhaengigkeiten mit `npm ci`, fuehrt die Tests aus, baut die App, listet `build/` auf und speichert das Ergebnis als Artefakt.
- `.github/workflows/docker.yml` baut das Docker-Image und pusht es nach `ghcr.io/<owner>/<repository>`. Auf `main` entstehen die Tags `latest` und `sha-<commit>`; Git-Tags wie `v1.0.0` werden ebenfalls uebernommen.

## Lokal testen

Wenn PowerShell aktuell im Ordner `C:\Users\TACSCDA2\Dev\Schule\324` steht, zuerst in den Projektordner wechseln:

```powershell
cd .\app
```

Danach die Befehle einzeln ausfuehren:

```powershell
npm ci
$env:CI = 'true'
npm test
npm run build
```

Fuer die folgenden Befehle muss Docker Desktop installiert und gestartet sein:

```powershell
docker build -t ref-card:local .
docker run --rm -p 8080:80 ref-card:local
```

Danach ist die App unter `http://localhost:8080` erreichbar.

Falls PowerShell meldet, dass `docker` nicht erkannt wird, Docker Desktop installieren bzw. starten und danach ein neues Terminal oeffnen. Mit `docker version` kann die Installation kontrolliert werden.

## GitHub vorbereiten

1. Ein leeres GitHub-Repository erstellen.
2. Dieses lokale Projekt mit dem neuen Repository verbinden und `main` pushen.
3. Unter **Actions** kontrollieren, ob `CI` und `Docker image` erfolgreich sind.
4. Unter **Packages** das erzeugte Container-Image pruefen.

Fuer ein oeffentliches GHCR-Image sind keine zusaetzlichen Registry-Secrets erforderlich. Der Workflow verwendet das automatisch vorhandene `GITHUB_TOKEN`.

## Optionales SSH-Deployment aktivieren

Das Deployment ist standardmaessig deaktiviert. In GitHub unter **Settings > Secrets and variables > Actions** folgende Repository-Secrets anlegen:

- `SSH_HOST`: Hostname oder IP des Servers
- `SSH_PORT`: SSH-Port, normalerweise `22`
- `SSH_USER`: SSH-Benutzer mit Docker-Berechtigung
- `SSH_PRIVATE_KEY`: privater SSH-Schluessel
- `GHCR_USERNAME`: GitHub-Benutzername, der das Image lesen darf
- `GHCR_TOKEN`: GitHub PAT mit mindestens `read:packages`

Danach die Repository-Variable `ENABLE_SSH_DEPLOY` auf `true` setzen. Auf dem Zielserver muessen Docker sowie der zugehoerige oeffentliche SSH-Schluessel eingerichtet sein. Der Container heisst `ref-card` und lauscht auf Port 80.

## GitHub-Remote setzen

Die Platzhalter ersetzen und anschliessend pushen:

```bash
git remote rename origin upstream
git remote add origin https://github.com/DEIN-BENUTZER/DEIN-REPOSITORY.git
git push -u origin main
```
