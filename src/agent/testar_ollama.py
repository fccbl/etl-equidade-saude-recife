import ollama

MODELO = "llama3.2"


def testar_ollama():
    resposta = ollama.chat(
        model=MODELO,
        messages=[
            {
                "role": "user",
                "content": "Você está funcionando? Responda em português, em uma frase curta.",
            }
        ],
    )
    print(resposta["message"]["content"])


if __name__ == "__main__":
    testar_ollama()
