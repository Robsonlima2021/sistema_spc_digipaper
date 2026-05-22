import fdb
import os
import sqlite3
import datetime

# --- CONFIGURAÇÕES ---
# Caminho da DLL do Firebird
FDB_DLL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fb_embed', 'fbclient.dll')
fdb.load_api(FDB_DLL_PATH)

# Caminho do banco Firebird
DB_FB_PATH = r"C:\Users\robso\Downloads\DADOSRR.FDB"
FB_USER = "sysdba"
FB_PASSWORD = "masterkey"

# Caminho do banco SQLite
DB_SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Sistema_Inadimplencia', 'contas_aberto.db')

def setup_sqlite():
    """Conecta no SQLite e garante que a tabela de histórico existe"""
    conn = sqlite3.connect(DB_SQLITE_PATH)
    cursor = conn.cursor()
    
    # Criação da tabela de histórico
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_codigo TEXT,
            numero_conta TEXT,
            venda_numero TEXT,
            data_vencimento DATE,
            data_pagamento DATE,
            valor REAL,
            valor_pago REAL,
            situacao TEXT
        )
    ''')
    
    # Limpa a tabela para não duplicar se rodar de novo
    cursor.execute('DELETE FROM historico')
    
    conn.commit()
    return conn

def connect_firebird():
    return fdb.connect(dsn=DB_FB_PATH, user=FB_USER, password=FB_PASSWORD, charset="UTF8")

def export_history():
    print("Conectando aos bancos de dados...")
    sqlite_conn = setup_sqlite()
    sqlite_cur = sqlite_conn.cursor()
    
    fb_conn = connect_firebird()
    fb_cur = fb_conn.cursor()
    
    # 1. Pegar todos os códigos de clientes que já estão no SQLite (os inadimplentes)
    sqlite_cur.execute("SELECT codigo FROM clientes WHERE codigo != '' AND codigo IS NOT NULL")
    clientes = [row[0] for row in sqlite_cur.fetchall()]
    
    print(f"Total de clientes inadimplentes encontrados: {len(clientes)}")
    print("Iniciando extração do histórico...")
    
    # Prepara a query de inserção no SQLite
    insert_query = '''
        INSERT INTO historico 
        (cliente_codigo, numero_conta, venda_numero, data_vencimento, data_pagamento, valor, valor_pago, situacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    '''
    
    # 2. Para cada cliente, busca o histórico no Firebird
    total_registros = 0
    for idx, cli_codigo in enumerate(clientes):
        fb_cur.execute('''
            SELECT 
                r.REC_NUMERO, 
                r.VEN_NUMERO, 
                r.REC_DATAVENC, 
                r.REC_DATAPAG, 
                r.REC_VALOR, 
                r.REC_VALORPAGO, 
                r.REC_SITUACAO
            FROM CONTASRECEBER r
            WHERE r.CLI_CODIGO = ?
            ORDER BY r.REC_DATAVENC DESC
        ''', (cli_codigo,))
        
        records = fb_cur.fetchall()
        
        for row in records:
            (rec_numero, ven_numero, venc, pag, valor, valor_pago, sit) = row
            
            # Formatar datas para YYYY-MM-DD
            venc_str = venc.strftime('%Y-%m-%d') if venc else None
            pag_str = pag.strftime('%Y-%m-%d') if pag else None
            
            v_num = str(ven_numero) if ven_numero else None
            c_num = str(rec_numero) if rec_numero else None
            
            v_val = float(valor) if valor else 0.0
            v_pago = float(valor_pago) if valor_pago else 0.0
            s = str(sit) if sit else ''
            
            sqlite_cur.execute(insert_query, (cli_codigo, c_num, v_num, venc_str, pag_str, v_val, v_pago, s))
            total_registros += 1
            
        if (idx + 1) % 100 == 0:
            print(f"Processados {idx + 1} de {len(clientes)} clientes...")
            sqlite_conn.commit()
            
    sqlite_conn.commit()
    print(f"\n[SUCESSO] Finalizado! {total_registros} registros de histórico importados para o contas_aberto.db.")
    
    fb_conn.close()
    sqlite_conn.close()

if __name__ == '__main__':
    export_history()
