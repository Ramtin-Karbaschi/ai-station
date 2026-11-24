# AI Station FAQ

Short answers for people who chat, upload documents, or generate media
on this station. Operators use [OPERATIONS.md](../OPERATIONS.md).

## How do I chat?

Open `http://127.0.0.1:3000` and sign in with your organization
account (SSO). Pick the general chat model
`Qwen3.8-27B-UD-Q4_K_M`. Applications do not use this page; they call
`http://127.0.0.1:4000/v1` with a project key.

## How do I upload documents (RAG)?

In Open WebUI go to **Workspace → Knowledge**, create a collection,
and upload PDF or text files. Ask in a chat with that collection
attached. Files stay on this host. Details:
[OPENWEBUI.md](OPENWEBUI.md).

## What is allowed use?

Use the station for your organization's own work on this machine.
Do not send prompts or documents to a public cloud from this product.
Follow your employer's data rules. Music, video, and image prompts
are hashed and filtered; the station does not keep the raw prompt
text. Illegal content is not allowed.

## Where is media?

ComfyUI is `http://127.0.0.1:8188` and uses the GPU exclusively. Stop
chat models before starting it. See [COMFYUI.md](COMFYUI.md).

## Who do I ask for access or backups?

Your station operator. They run `ai status`, `ai sso`, and backups.
This FAQ does not replace SSO setup or disaster recovery.
