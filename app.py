                    try:
                        with st.spinner("Gerando boleto no Asaas..."):
                            boleto = emitir_boleto_asaas(
                                arquivo.name,
                                faturamento,
                                valor_final_boleto,
                                vencimento,
                                descricao_boleto,
                                emitir_nota_apos_pagamento
                            )

                        st.session_state[f"resultado_boleto_{indice}"] = boleto

                    except Exception as erro_boleto:
                        st.error(
                            f"Não foi possível emitir o boleto: {erro_boleto}"
                        )

                boleto_salvo = st.session_state.get(
                    f"resultado_boleto_{indice}"
                )

                if boleto_salvo:
                    if boleto_salvo.get("novo"):
                        st.success(
                            f"✅ Boleto criado para "
                            f"{boleto_salvo.get('clienteNome', '')} "
                            f"(BOX {boleto_salvo.get('box', '')}) "
                            f"e notificações padronizadas com sucesso. "
                            f"ID: {boleto_salvo.get('id', '')}"
                        )
                    else:
                        st.info(
                            "ℹ️ Esta cobrança já existia no Asaas. "
                            "O sistema não gerou uma cobrança duplicada."
                        )

                    if boleto_salvo.get("invoiceUrl"):
                        st.link_button(
                            "🔗 Abrir cobrança no Asaas",
                            boleto_salvo["invoiceUrl"],
                            use_container_width=True
                        )

                    if boleto_salvo.get("bankSlipUrl"):
                        st.link_button(
                            "📄 Abrir boleto",
                            boleto_salvo["bankSlipUrl"],
                            use_container_width=True
                        )

            resultados.append({
                "Arquivo": arquivo.name,
                "Faturamento": faturamento,
                "Royalties 4%": royalties,
            })

            detalhes_exportacao[
                arquivo.name
            ] = editada.copy()

            total_faturamento += faturamento
            total_royalties += royalties

        except Exception as erro:
            st.error(
                f"Erro ao processar {arquivo.name}: {erro}"
            )

            resultados.append({
                "Arquivo": arquivo.name,
                "Faturamento": 0.0,
                "Royalties 4%": 0.0,
            })

    st.divider()

    col_total1, col_total2 = st.columns(2)

    col_total1.metric(
        "Faturamento total geral",
        formatar_moeda(total_faturamento)
    )
    
    col_total2.metric(
        "Royalties 4% total",
        formatar_moeda(total_royalties)
    )
    
    # ========================================================
    # DOWNLOAD DO RELATÓRIO GERAL
    # ========================================================
    
    resumo = pd.DataFrame(resultados)

    excel_geral = gerar_excel_geral(
    resumo,
    detalhes_exportacao
)
    
    st.download_button(
        "📥 Baixar relatório geral em Excel",
        data=excel_geral,
        file_name="relatorio_geral_faturamento.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
