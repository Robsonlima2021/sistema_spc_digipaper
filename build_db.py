import sqlite3
import re
import os

def create_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            nome TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contas (
            numero TEXT PRIMARY KEY,
            venda TEXT,
            cliente_id INTEGER,
            vencimento DATE,
            situacao TEXT,
            valor_parcela REAL,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conta_numero TEXT,
            codigo TEXT,
            descricao TEXT,
            qtd REAL,
            unitario REAL,
            total REAL,
            FOREIGN KEY(conta_numero) REFERENCES contas(numero)
        )
    ''')
    
    conn.commit()
    return conn

def parse_txt_to_db(txt_path, conn):
    if not os.path.exists(txt_path):
        print(f"Erro: Arquivo {txt_path} não encontrado.")
        return
        
    with open(txt_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
        
    # The regex for [CLIENTE] captures code and name or just name
    re_cliente = re.compile(r'^\[CLIENTE\] (?:(.*?) - )?(.*)') 
    re_conta = re.compile(r'^\s*\[CONTA Nº (.*?)\] Venda: (.*?) \| Vencimento: (.*?) \| Situação: (.*?) \| Valor da Parcela: (.*)')
    re_item = re.compile(r'^\s*\[Item\] (.*?)\s+-\s+(.*?)\s+\| Qtd: (.*?)\s+\| Unit: (.*?)\s+\| Total: (.*)')
    
    cursor = conn.cursor()
    
    current_cliente_id = None
    current_conta_num = None
    
    for line in lines:
        line_strip = line.strip('\n')
        
        m_cli = re_cliente.search(line_strip)
        if m_cli:
            cod = m_cli.group(1) if m_cli.group(1) else ""
            nome = m_cli.group(2).strip()
            
            cursor.execute('INSERT INTO clientes (codigo, nome) VALUES (?, ?)', (cod, nome))
            current_cliente_id = cursor.lastrowid
            continue
            
        m_conta = re_conta.search(line_strip)
        if m_conta:
            num_conta, venda, vencimento, sit, valor_str = [m.strip() for m in m_conta.groups()]
            
            valor_str = valor_str.replace('R$', '').replace(',', '').strip()
            try:
                valor_parcela = float(valor_str)
            except:
                valor_parcela = 0.0
                
            try:
                d, m, y = vencimento.split('/')
                vencimento_date = f"{y}-{m}-{d}"
            except:
                vencimento_date = vencimento
            
            cursor.execute('''
                INSERT OR IGNORE INTO contas (numero, venda, cliente_id, vencimento, situacao, valor_parcela)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (num_conta, venda, current_cliente_id, vencimento_date, sit, valor_parcela))
            current_conta_num = num_conta
            continue
            
        m_item = re_item.search(line_strip)
        if m_item:
            cod_item, desc, qtd_str, unit_str, total_str = [m.strip() for m in m_item.groups()]
            
            try:
                qtd = float(qtd_str.replace(',', ''))
                unit = float(unit_str.replace('R$', '').replace(',', '').strip())
                total = float(total_str.replace('R$', '').replace(',', '').strip())
            except:
                qtd = 0.0; unit = 0.0; total = 0.0
                
            cursor.execute('''
                INSERT INTO itens (conta_numero, codigo, descricao, qtd, unitario, total)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (current_conta_num, cod_item, desc, qtd, unit, total))
            continue
            
    conn.commit()
    print("Dados processados com sucesso!")

if __name__ == "__main__":
    db_path = "contas_aberto.db"
    txt_path = "Relatorio_Contas_Aberto.txt"
    
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = create_db(db_path)
    parse_txt_to_db(txt_path, conn)
    
    # Just to confirm data
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM clientes")
    cli_c = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM contas")
    con_c = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM itens")
    it_c = c.fetchone()[0]
    
    print(f"Total Clientes: {cli_c}")
    print(f"Total Contas: {con_c}")
    print(f"Total Itens: {it_c}")
    
    conn.close()
