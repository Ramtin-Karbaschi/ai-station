# AI Station Windows Launchers

## Which file should I use?

| File | Role |
|---|---|
| **AI Station.cmd** | Quick start: start platform + open Open WebUI in your **default browser** (keeps your login). Press ENTER in the console to stop. |
| **AI Station Manager.cmd** | Full control panel: platform, model switching, **application API keys**, logs, backup. |
| **AI Station Admin.cmd** | Compatibility alias → opens Manager. |

Use **Manager** for day-to-day operations and API management. Use **AI Station.cmd** only when you want a one-click start/stop around a chat session.

## Why the old AI Station.cmd felt like a different account

Older builds opened Microsoft Edge with an isolated profile under:

```text
%LOCALAPPDATA%\AIStation\BrowserProfile
```

That profile had no cookies or Open WebUI session, so it looked like a foreign/shared account. The quick-start launcher now opens your **default browser** instead.

## Open WebUI login

Default admin on this workstation:

```text
ramtin.karbaschi@gmail.com
```

If login fails with “email or password incorrect” / 401:

1. Open **AI Station Manager.cmd**
2. Choose **26. Reset Open WebUI password**
3. Sign in with the password printed once in that window

`AI Station.cmd` now waits until WebUI is ready, opens your **default browser**, and **keeps the platform running** after the window closes (stop via Manager).


Menu section **Application API**:

- API info + project list
- Create project API key
- Show / revoke project
- Open `projects/` folder (credential `.env` files)

Endpoint for apps:

```text
http://127.0.0.1:4000/v1
```

LiteLLM admin UI:

```text
http://127.0.0.1:4000/ui
```
