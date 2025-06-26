import os
import openai
from dotenv import load_dotenv
import time

# Carrega variáveis do .env
load_dotenv()

# Variáveis de ambiente
api_key = os.getenv("OPENAI_API_KEY")
assistant_id = os.getenv("ASSISTENTE_REVISOR_TEXTUAL")

# Verificações iniciais
print("🔐 OPENAI_API_KEY:", api_key[:10], "...")
print("🤖 ASSISTANT_REVISOR_TEXTUAL:", assistant_id)

# Configura a API Key
openai.api_key = api_key

# Cria thread e executa teste
try:
    print("📤 Enviando mensagem de teste...")
    thread = openai.beta.threads.create()
    openai.beta.threads.messages.create(thread_id=thread.id, role="user", content="Teste de revisão: A informacao esta incorreta.")
    
    run = openai.beta.threads.runs.create(thread_id=thread.id, assistant_id=assistant_id)

    while True:
        run = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        print("⏳ Status:", run.status)
        if run.status == "completed":
            break
        elif run.status in ["failed", "cancelled"]:
            print("❌ Assistente falhou ou foi cancelado.")
            exit()
        time.sleep(2)

    # Recupera resposta final
    mensagens = openai.beta.threads.messages.list(thread_id=thread.id)
    for msg in reversed(mensagens.data):
        if msg.role == "assistant":
            print("\n📥 Resposta do assistente:")
            print(msg.content[0].text.value.strip())
            break

except Exception as e:
    print("❌ Erro durante execução:", str(e))
