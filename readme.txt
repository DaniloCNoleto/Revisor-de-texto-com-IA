# Revisor Inteligente Dossel — Entrega Final

## Scripts
1. `revisor_dossel_v2_final.py`: realiza revisão textual com assistente especializado e registra alterações.
2. `verificador_bibliografico_final.py`: valida fontes e formatações ABNT/padrão Dossel, podendo corrigir.
3. `track_changes_final.py`: aplica Track Changes comparando o original e o documento final revisado.

## Saídas
- /saida/documento_revisado.docx             ← Documento com revisões aplicadas
- /saida/documento_revisado-trackchanges.docx← Documento com alterações visíveis
- /saida/relatorio_tecnico.docx              ← Detalhamento por tipo de revisão
- /saida/avaliacao_quantitativa.xlsx         ← Dados estruturados com score de alteração
- /saida/checkpoint.txt                      ← Parágrafo de retomada em caso de falha
- /saida/falhas.csv                          ← Parágrafos com falha
- /saida/tempo_total.txt                     ← Duração total da execução
- /saida/tempo_por_paragrafo.txt             ← Tempo individual por parágrafo

## Execução
- Rode `revisor_dossel_v2_final.py` primeiro
- Ao terminar com sucesso, ele inicia `verificador_bibliografico_final.py`
- Por fim, será executado `track_changes_final.py` automaticamente
