# Deployment über GitHub Actions und SSH (Aufgabe 20.1)

## Umsetzung und aktueller Stand

Dieses Repository enthält **React / Ref.Card 02**, keine Spring-Boot-Anwendung.
Die Aufgabe nennt widersprüchlich Ref.Card 01 und 02. Wie vereinbart wird das
vorhandene React-Projekt verwendet: `npm run build` erzeugt statische Dateien,
Nginx liefert sie auf Port **8080** aus. Maven, Java und eine JAR-Datei sind hier
nicht nötig. Das Lernziel (Build, SSH, cloud-init, Secrets, systemd) bleibt erhalten.

Vorbereitet sind CI/CD, Cloud-Config, zwei lokale Ed25519-Schlüssel,
`deploy.sh`, eine systemd-Unit, Gesundheitsprüfung und automatisches Zurückschalten
auf die vorherige Version bei einem fehlgeschlagenen Start.
Die EC2-Instanz `i-0cdd2539e1d05e972` (`m324-react`) wurde in `us-east-1`
mit Ubuntu 24.04, t2.micro und 8 GiB gp3 erstellt. Ihre öffentliche Adresse lautet
aktuell `3.83.172.230` (kann sich nach Stop/Start ändern).
Der Windows-Runner `m324-ec2-deploy` ist unter
`C:\Users\TACSCDA2\actions-runner-m324` installiert und registriert.
Die nachfolgenden Kapitel erklären die Einrichtung zum Nachvollziehen.

Lokal geprüft: React-Test bestanden (1/1), Produktionsbuild erfolgreich,
YAML- und Bash-Syntax gültig. Eine isolierte Simulation mit ersetzten Systembefehlen
prüfte Erstdeployment, fehlgeschlagene HTTP-Prüfung, Rückkehr zur vorherigen Version
und ein nachfolgendes erfolgreiches Deployment. Das ersetzt noch keinen echten
Test von Nginx, systemd, SSH und cloud-init auf Ubuntu/EC2.

## 1. SSH-Schlüssel

Bereits erzeugt, ausserhalb des Repositories:

| Zugriff | Privater Schlüssel auf deinem Windows-PC | Verwendung |
|---|---|---|
| Administration | `C:\Users\TACSCDA2\.ssh\m324_admin_key` | Nur für deinen persönlichen SSH-Zugang |
| Deployment | `C:\Users\TACSCDA2\.ssh\m324_deploy_key` | Vollständiger Inhalt wird GitHub-Secret `EC2_SSH_KEY` |

Die Dateien mit Endung `.pub` sind die öffentlichen Schlüssel. Beide stehen bereits
in der lokal generierten, durch `.gitignore` ausgeschlossenen `cloud-config.local.yaml`.
`cloud-config.yaml` ist die wiederverwendbare Vorlage mit zwei zu ersetzenden Platzhaltern.
**Für EC2 die fertige lokale Datei verwenden.** Private Schlüssel niemals committen.

Für die automatische Erzeugung wurden beide Schlüssel ohne Passphrase angelegt.
Schütze den Admin-Schlüssel vor der Verwendung interaktiv mit einer eigenen Passphrase:

```powershell
ssh-keygen -p -f "$env:USERPROFILE/.ssh/m324_admin_key"
```

Bei der bisherigen Passphrase einfach Enter drücken; danach die neue Passphrase
zweimal eingeben. Der öffentliche Schlüssel und die Cloud-Config bleiben gültig.
Der Deployment-Schlüssel bleibt für den unbeaufsichtigten Workflow ohne Passphrase.

Zum Nachvollziehen wären die Erstellungsbefehle (vorhandene Dateien nicht überschreiben):

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE/.ssh/m324_admin_key" -C "m324-admin-zugriff"
ssh-keygen -t ed25519 -f "$env:USERPROFILE/.ssh/m324_deploy_key" -C "m324-github-actions-deploy"
```

**Vertiefungsfrage:** Mit einem gemeinsamen Schlüssel würden beide Zugriffe dieselbe
Identität verwenden. Ein Leak in der Pipeline würde auch den persönlichen Zugang
kompromittieren. Widerruf und Austausch würden beide Zugriffe gleichzeitig betreffen.
Zwei Schlüssel ermöglichen getrennten Widerruf. Da beide hier `ubuntu` und dessen
unbeschränktes sudo verwenden, bewirken sie allein **keine Trennung der Rechte**.

## 2. EC2 im AWS Learner Lab erstellen

1. AWS Academy öffnen, **Start Lab**, grünes AWS-Symbol abwarten und AWS-Konsole öffnen.
2. Region und verbleibendes Budget prüfen. EC2 → **Launch instance**.
3. Name `m324-react`, Ubuntu Server **24.04 LTS**, Typ **t2.micro**, sofern im Lab verfügbar.
4. **Proceed without a key pair** wählen; die Schlüssel kommen aus cloud-init.
5. Öffentliches Subnetz mit Route zum Internet-Gateway und öffentlicher IPv4 verwenden.
6. Security Group: TCP **22** nur von deiner öffentlichen IP (`/32`, **My IP**),
   TCP **8080** von `0.0.0.0/0`. Ausgehender Internetzugriff muss für Paketinstallation möglich sein.
7. Unter **Advanced details → User data** den kompletten Inhalt von
   `cloud-config.local.yaml` einfügen. Nicht die Vorlage mit Platzhaltern verwenden.
8. Instanz starten, Statuschecks und cloud-init abwarten. Öffentliche IPv4 notieren.

Die Cloud-Config installiert Nginx, curl und flock (`util-linux`), hinterlegt beide
öffentlichen Schlüssel und deaktiviert den allgemeinen Nginx-Dienst. Unser eigener
Dienst `ref-card.service` wird beim ersten Deployment installiert und aktiviert.
User-Data läuft grundsätzlich bei der ersten Einrichtung; nachträgliches Ändern der
Datei auf deinem PC verändert keine bestehende Instanz.

Erster Zugang (PowerShell):

```powershell
$ec2Host = 'DEINE-OEFFENTLICHE-IP'
ssh -i "$env:USERPROFILE/.ssh/m324_admin_key" "ubuntu@$ec2Host"
```

Den angebotenen **Host-Fingerprint** vor dem Bestätigen über einen unabhängigen Kanal
prüfen, beispielsweise die EC2-Systemausgabe (cloud-init protokolliert Host-Key-Fingerprints)
oder eine verfügbare AWS-Konsole-Verbindung. Über diesen vertrauenswürdigen Zugang kann
`sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` den Fingerprint anzeigen.
Ein Fingerprint aus einer ungeprüften SSH-Verbindung allein genügt nicht.

Auf EC2 prüfen:

```bash
sudo cloud-init status --wait
sudo cloud-init status --long
nginx -v
ls -ld /home/ubuntu/incoming /opt/ref-card/releases
```

Vor dem ersten Deployment antwortet Port 8080 noch nicht.

## 3. Die SSH-Netzwerkfrage lösen

**My IP erlaubt deinem PC den Zugriff, aber keinem normalen GitHub-gehosteten Runner.**
Die konkrete Lösung in `ci.yml` ist deshalb ein **eigener Deploy-Runner im selben
Netz wie dein PC**, beispielsweise direkt auf Windows mit Git Bash. Nur der Deploy-Job läuft dort;
Build und Tests laufen auf `ubuntu-latest` bei GitHub.

1. In deinem Repository `dami54ano/M324` zu **Settings → Actions → Runners →
   New self-hosted runner** gehen und **Windows x64** auswählen.
2. Die dort aktuell angezeigten Download- und Registrierungsbefehle in PowerShell
   ausführen. Ein separates Runner-Verzeichnis ausserhalb des Projekts verwenden.
3. Bei den zusätzlichen Labels **ec2-deploy** angeben. Die Standardlabels
   `self-hosted` und das automatisch vergebene Betriebssystemlabel beibehalten.
4. Git for Windows mit Git Bash muss installiert sein (hier bereits vorhanden).
   Der Workflow führt seine Shell-Schritte ausdrücklich mit Bash aus. Unter Linux
   alternativ `git`, `openssh-client` und `curl` installieren und Linux x64 registrieren.

5. Unter Windows mit `.\run.cmd`, unter Linux mit `./run.sh` im Runner-Verzeichnis starten und das Terminal während des
   Deployments offen lassen. In GitHub muss der Runner **Idle** anzeigen.
6. Der Runner muss dieselbe öffentliche Ausgangs-IP wie **My IP** benutzen.
   Bei VPN oder anderem Netz die tatsächliche Runner-IP als eigene `/32`-Regel freigeben.
   Vom Runner-Rechner z.B. `ssh -i /PFAD/ZUM/ADMIN_KEY ubuntu@HOST` testen.

Der Runner erhält Jobs über ausgehendes HTTPS; es ist keine eingehende Verbindung
von GitHub zu deinem PC erforderlich. Setze ihn nur für vertrauenswürdigen Code ein.
Pull Requests laufen hier ausschliesslich auf GitHub-gehosteten Build-Runnern.
Ein eigener Runner kann dennoch grundsätzlich von weiteren Repo-Workflows angesprochen
werden: Schreibrechte und Workflow-Änderungen entsprechend schützen.

Eine Alternative ist ein GitHub-Runner mit fester Ausgangs-IP. Dann `runs-on` im
Deploy-Job auf dessen Label ändern und diese IP in der Security Group freigeben.
Ein einfacher Wechsel auf `ubuntu-latest` ohne Netzwerklösung funktioniert nicht.

## 4. GitHub-Secrets setzen

Unter **Settings → Secrets and variables → Actions → Secrets** anlegen:

| Secret | Inhalt |
|---|---|
| `EC2_HOST` | Öffentliche IPv4 oder DNS-Name, ohne `http://` und ohne Port |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | Vollständiger privater `m324_deploy_key`, inklusive BEGIN/END-Zeilen |
| `EC2_KNOWN_HOSTS` | Verifizierter SSH-Host-Key-Eintrag für genau diesen Host |

Nach dem überprüften ersten Login kann der Host-Key-Eintrag lokal ermittelt werden:

```powershell
ssh-keygen -F $ec2Host -f "$env:USERPROFILE/.ssh/known_hosts"
```

Die passende Schlüsselzeile (keine `#`-Kommentarzeile) als `EC2_KNOWN_HOSTS` hinterlegen.
Bei mehreren Schlüsselzeilen können alle übernommen werden. Auch gehashte Hostnamen
sind zulässig, solange sie zum verwendeten `EC2_HOST` passen.
Der Workflow benutzt `StrictHostKeyChecking=yes`; er vertraut nicht blind auf
`ssh-keyscan` während des Deployments.

Den Deployment-Schlüssel ohne Terminalausgabe in die Zwischenablage kopieren:

```powershell
Get-Content -Raw "$env:USERPROFILE/.ssh/m324_deploy_key" | Set-Clipboard
```

In das Secret-Feld einfügen, speichern und danach die Zwischenablage leeren:

```powershell
Set-Clipboard -Value ''
```

Unter **Settings → Environments** das Environment **production** anlegen.
Dort bei Bedarf main als erlaubten Deployment-Branch setzen.
Unter **Actions → Variables** die Repository-Variable **ENABLE_EC2_DEPLOY = true** setzen,
sobald EC2, Secrets und Runner bereit sind. Vorher wird der Deploy-Job bewusst übersprungen.
Die früheren `SSH_*`-/`GHCR_*`-Deploy-Secrets und `ENABLE_SSH_DEPLOY` werden nicht mehr
verwendet; der Docker-Workflow veröffentlicht weiterhin das Image, führt aber kein
zweites konkurrierendes SSH-Deployment aus.

## 5. Pipeline starten und prüfen

Im Projektordner `app` nach Durchsicht der Änderungen:

```powershell
git add .github/workflows/ci.yml .github/workflows/docker.yml .gitattributes .gitignore cloud-config.yaml deploy.sh deployment DEPLOYMENT.md README.md
git commit -m "Add EC2 SSH deployment with systemd and rollback"
git push origin main
```

`cloud-config.local.yaml` und die privaten Schlüssel werden dabei nicht aufgenommen.
Danach **Actions → CI** öffnen. Alternativ nach dem Push unter **Run workflow** manuell starten.

Ablauf:

1. `npm ci` installiert die im Lockfile festgelegten Abhängigkeiten.
2. Der React-Test läuft; bei einem Fehler gibt es kein Deployment.
3. `npm run build` erzeugt den Build. `upload-artifact` speichert ihn im Workflow-Lauf.
4. `deploy` wartet durch `needs: build` auf den erfolgreichen Build. Er läuft nur auf
   main und bei aktivierter Variable, niemals für einen Pull Request.
5. `download-artifact` lädt genau diesen Build. Der Workflow ergänzt `version.txt`
   mit Commit-SHA, Lauf-ID und Versuch und kopiert Build, Konfiguration und Skript per SCP.
6. SSH startet `deploy.sh` auf EC2. Das Skript sperrt parallele Deployments mit `flock`,
   prüft die Eingaben und kopiert eine neue Version nach `/opt/ref-card/releases/`.
7. Nach der Nginx-Syntaxprüfung schaltet es den Symlink `current` um, installiert die
   systemd-Unit und führt `systemctl restart ref-card.service` aus.
8. Eine lokale HTTP-Prüfung verifiziert Dienststatus, Startseite und Versionskennung.
   Schlägt der Neustart oder die Prüfung fehl, wird die vorherige Version wieder gestartet.
   Beim allerersten Deployment ohne Vorgänger wird der fehlerhafte Dienst deaktiviert.
9. Der Runner prüft zusätzlich die Versionskennung über die öffentliche Adresse.
   Ein ausschliesslich externer Netzwerkfehler markiert den Job rot, löst aber keinen
   Rollback eines lokal gesunden Dienstes aus.

Mehrere Deploy-Jobs werden serialisiert; es wird kein laufender Neustart abgebrochen.
GitHub garantiert innerhalb der Concurrency-Gruppe keine FIFO-Reihenfolge. Wenn ältere
Läufe nachträglich manuell wiederholt werden, können sie eine ältere Version ausrollen.

Öffne **http://DEINE-OEFFENTLICHE-IP:8080** im Browser. Unter `/version.txt` steht die
Release-ID. Nach einem Lab-Neustart die aktuelle IP, `EC2_HOST`, Host-Key-Zuordnung
und bei Bedarf die My-IP-Regel prüfen und aktualisieren.

Auf EC2:

```bash
sudo systemctl status ref-card.service --no-pager
sudo journalctl -u ref-card.service -n 80 --no-pager
curl -f http://127.0.0.1:8080/version.txt
readlink -f /opt/ref-card/current
```

Für den Nachweis der Aufgabe Screenshots des grünen CI-/Deploy-Laufs, der Browserseite
mit Adresse, der Security Group und des aktiven systemd-Dienstes aufnehmen. Keine Secrets abbilden.

## 6. Zusatzaufgabe: systemd statt pkill/nohup

`deployment/ref-card.service` beschreibt den Prozess eindeutig. systemd startet Nginx
beim Booten, beendet es kontrolliert über SIGQUIT und startet es bei einem Absturz
neu (`Restart=on-failure`). Status und Logs sind über `systemctl` und `journalctl`
verfügbar. Die Worker laufen als `www-data`; der Nginx-Master startet als root.

`pkill -f ...` sucht dagegen nach einem Text in Kommandozeilen und kann ungewollt
weitere Prozesse treffen. `nohup ... &` verhindert im Wesentlichen das Beenden durch
SIGHUP beim Logout; es überwacht den Prozess nicht und richtet keinen Boot-Autostart ein.

**Warum `pkill ... || true`?** Wenn kein passender Prozess existiert, liefert `pkill`
einen Fehlerstatus. `|| true` macht diesen erwarteten Fall erfolgreich, damit etwa ein
Skript mit `set -e` weiterläuft. Im einfachen PDF-Skript ohne `set -e` würde Bash meist
auch ohne diesen Zusatz fortfahren. Der Zusatz verschluckt allerdings auch andere
pkill-Fehler; deshalb darf er nicht pauschal hinter Build- oder Neustartbefehlen stehen.
Unser Skript verwendet systemd und beendet fehlgeschlagene Deployments mit Fehlerstatus.

Der Neustart verursacht eine kurze Unterbrechung. Symlink und Rollback reduzieren Risiken,
stellen aber kein unterbrechungsfreies Deployment dar. Auch bei einem Rollback können
Infrastrukturfehler den Wiederanlauf verhindern. Nach einem roten Job die Logs prüfen.

## 7. Reflexion

### 8.1 Sicherheitsarchitektur

Der Admin-Schlüssel bleibt persönlich auf dem PC und sollte eine Passphrase haben.
Der Deploy-Schlüssel liegt zusätzlich verschlüsselt als GitHub-Secret und während des
Jobs kurz in einer temporären Datei auf dem Runner. Diese wird beim Jobende gelöscht.
Ein hart abgebrochener Rechner kann die Bereinigung verhindern; der Runner muss deshalb
als vertrauenswürdiger Rechner behandelt werden.
Bei Verlust eines Schlüssels dessen öffentliche Zeile in `~ubuntu/.ssh/authorized_keys`
entfernen, einen Ersatz erzeugen und nur die betroffene Hinterlegung aktualisieren.
Bei einem Deploy-Leak auch GitHub-Secret ersetzen und Actions-/Server-Logs kontrollieren.

In Unternehmen sind getrennte Identitäten für Personen und Automatisierung sinnvoll,
weil Verantwortlichkeit, Rotation und Sperrung getrennt funktionieren. Hier besitzen
beide Schlüssel trotzdem sudo-Vollzugriff. Eine produktive Weiterentwicklung wäre ein
separater Deploy-Benutzer mit eng begrenztem, root-eigenem Deployment-Helfer.

### 8.2 Netzwerksicherheit

| Ansatz | Sicherheit | Aufwand / Bewertung |
|---|---|---|
| GitHub-IP-Ranges freigeben | Breite, geteilte Netze statt nur eines Runners; IP-Filter ersetzt keine SSH-Authentisierung | Viele und veränderliche Bereiche; laufende Pflege. GitHub empfiehlt für Allowlisting eher feste oder eigene Runner. Für dieses Lab unpraktisch. |
| Eigener Runner mit bekannter Ausgangs-IP | Nur diese `/32` benötigt Port 22; Runner muss geschützt sein | Registrierung und Betrieb nötig. Hier gewählt: Windows mit Git Bash im eigenen Netz, passend zu My IP. |
| AWS Systems Manager | Kein eingehender Port 22 erforderlich; Zugriff über IAM | SSM Agent, Instanzrolle, Netzwerkanbindung und Workflow-AWS-Authentisierung nötig; verfügbare IAM-Rechte im Learner Lab prüfen. Für automatisierte Befehle SSM Run Command statt einer interaktiven Sitzung verwenden. |
| Bastion Host | Zielserver-SSH nur von der Bastion, zentraler Zugangspunkt | Zusätzliche VM, Updates und Kosten. GitHub braucht weiterhin einen abgesicherten Weg zur Bastion; allein löst sie wechselnde Runner-IPs nicht. |

Quellen: [GitHub-Runner und IP-Adressen](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[eigene Runner](https://docs.github.com/en/actions/reference/runners/self-hosted-runners),
[AWS Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html).
Die Wahl eines eigenen Deploy-Runners ist eine Bewertung für dieses kleine Lab.

### 8.3 Deployment-Strategien

| Ansatz | Ausfallsicherheit | Komplexität |
|---|---|---|
| Dieses SSH-/systemd-Deployment | Kurzer Neustart; vorheriger Release bleibt für Rollback erhalten; eine EC2 bleibt ein einzelner Ausfallpunkt | Wenige Komponenten, gut nachvollziehbar; Host und SSH-Zugang selbst pflegen |
| Docker auf einer EC2 | Versionierte Images vereinheitlichen Laufzeit und erleichtern Rückkehr zu einem Image; beim Ersetzen eines einzelnen Containers weiterhin Unterbrechung | Registry und Container-Laufzeit zusätzlich nötig; vorhandener Docker-Workflow liefert bereits Images |
| Blue-Green mit zwei Umgebungen und Load Balancer | Neue Umgebung vor Umschaltung prüfbar, schnelle Rückschaltung; höherer Ressourcenbedarf | Zwei Umgebungen, Routing, Healthchecks und ggf. Datenmigration koordinieren |

Für dieses Lernprojekt genügt SSH mit systemd. Für höhere Verfügbarkeit wäre Blue-Green
mit Lastverteilung passender; Docker allein garantiert keine hohe Verfügbarkeit.

### 8.4 Ressourcen und Budget

Nach dem Nachweis den Runner mit Ctrl+C stoppen und `ENABLE_EC2_DEPLOY` auf `false`
setzen, wenn vorerst keine Deployments gewünscht sind. Im Learner Lab **End Lab**
verwenden und in EC2 prüfen, ob die Instanz tatsächlich gestoppt ist. Eine gestoppte
Instanz kann weiterhin kostenpflichtigen Speicher besitzen. Budgetanzeige sowie
unbenutzte EBS-Volumes, Snapshots und öffentliche IP-Ressourcen kontrollieren.
Nach endgültigem Abschluss die eindeutig zu dieser Übung gehörenden, nicht mehr
benötigten Ressourcen löschen und vorher benötigte Nachweise sichern.
Kein `terraform destroy` oder pauschales Löschen fremder Lab-Ressourcen verwenden.

Alte Releases und Uploads bleiben absichtlich erhalten, damit ein Rollback möglich ist.
Gelegentlich `sudo du -sh /opt/ref-card/releases /home/ubuntu/incoming` kontrollieren
und nur gezielt nicht mehr benötigte Releases entfernen; aktive und letzte funktionierende
Version behalten. Nach Ende der Übung Deploy-Secret und autorisierten Deploy-Key widerrufen.

**Anwendungsstatus:** Die Instanz wurde für die Übung erstellt. Nach dem Nachweis
müssen Instanz und Runner beendet werden; bestehende Ressourcen nicht pauschal löschen.

## Lokal prüfen und Fehler eingrenzen

Im Ordner `app`:

```powershell
npm ci
$env:CI = 'true'
npm test
npm run build
```

Das Projekt legt Node 20 / npm 10 fest. Lokal war Node 22 / npm 11 vorhanden;
für identische Bedingungen die Projektversionen verwenden.

| Symptom | Prüfen |
|---|---|
| Deploy übersprungen | main, `ENABLE_EC2_DEPLOY=true`, kein Pull Request |
| Waiting for a runner | Runner online und Labels `self-hosted`, `ec2-deploy` vorhanden |
| SSH timeout | Lab aktiv, aktuelle IP, Route/öffentliche IP, SG-Port 22 und tatsächliche Runner-Ausgangs-IP |
| Permission denied (publickey) | `EC2_USER=ubuntu`, richtiger Deploy-Key, cloud-init fertig |
| Host key verification failed | Hostname/IP passt zur unabhängig überprüften `EC2_KNOWN_HOSTS`-Zeile |
| Browser nicht erreichbar | SG-Port 8080, `systemctl status`, `journalctl`, lokales curl |
| Nginx bind failed | Port 8080 bereits belegt: `sudo ss -ltnp`; konkurrierenden Dienst identifizieren |
| Deployment fehlgeschlagen | Actions-Log und Dienst-Log lesen; aktive Release-ID nach Rollback prüfen |

Weitere Quellen: [Cloud-Config-Beispiele](https://cloudinit.readthedocs.io/topics/examples.html),
[Build-Artefakte zwischen Jobs](https://docs.github.com/en/actions/tutorials/store-and-share-data),
[Nginx-Startparameter](https://nginx.org/en/docs/switches.html).
