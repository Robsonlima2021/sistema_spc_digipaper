import fdb
import psycopg2
import os

# --- CONFIGURAÇÕES FIREBIRD ---
FDB_DLL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fb_embed', 'fbclient.dll')
fdb.load_api(FDB_DLL_PATH)
DB_FB_PATH = r"C:\Users\robso\Downloads\DADOSRR.FDB"
FB_USER = "sysdba"
FB_PASSWORD = "masterkey"

# --- CONFIGURAÇÕES POSTGRESQL ---
PG_HOST = "127.0.0.1"
PG_USER = "postgres"
PG_PASSWORD = "postgres"
PG_DB = "control"

def sync_data():
    print("Conectando ao Firebird...")
    fb_conn = fdb.connect(dsn=DB_FB_PATH, user=FB_USER, password=FB_PASSWORD, charset="UTF8")
    fb_cur = fb_conn.cursor()
    
    print("Conectando ao PostgreSQL...")
    pg_conn = psycopg2.connect(dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, host=PG_HOST)
    pg_cur = pg_conn.cursor()
    
    # Registra o usuário da sessão para que as triggers de log não falhem
    pg_cur.execute("SELECT get_usuario(1)")
    
    print("Buscando clientes inadimplentes no Firebird...")
    # Fetch open accounts from Firebird
    fb_cur.execute('''
        SELECT c.CLI_CODIGO, c.CLI_NOME, c.CLI_CPF_CNPJ, c.CLI_ENDERECO, c.CLI_BAIRRO, c.CLI_CEP, c.CLI_FONE, c.CLI_DATACADASTRO,
               r.REC_NUMERO, r.REC_VALOR, r.REC_DATAVENC
        FROM CLIENTES c
        JOIN CONTASRECEBER r ON r.CLI_CODIGO = c.CLI_CODIGO
        WHERE (r.REC_DATAPAG IS NULL OR r.REC_VALORPAGO < r.REC_VALOR)
          AND r.REC_SITUACAO = 'A'
    ''')
    records = fb_cur.fetchall()
    print(f"Total de faturas em aberto encontradas: {len(records)}")
    
    clientes_processados = set()
    parcelas_inseridas = 0
    
    for row in records:
        (cli_codigo, cli_nome, cli_cpf_cnpj, cli_end, cli_bairro, cli_cep, cli_fone, cli_datacadastro,
         rec_numero, rec_valor, rec_datavenc) = row
         
        # Evitar erros de NOT NULL no Postgres
        cli_cpf_cnpj = cli_cpf_cnpj if cli_cpf_cnpj else ''
        cli_nome = cli_nome if cli_nome else 'CLIENTE SEM NOME'
        cli_end = cli_end if cli_end else ''
        cli_bairro = cli_bairro if cli_bairro else ''
        cli_cep = cli_cep if cli_cep else ''
        cli_fone = cli_fone if cli_fone else ''
         
        # Verifica e cadastra o cliente, se não existir
        if cli_codigo not in clientes_processados:
            pg_cur.execute("SELECT codigo FROM clientes WHERE codigo = %s", (cli_codigo,))
            if not pg_cur.fetchone():
                # Verificar se o CEP existe em cidades
                if cli_cep:
                    pg_cur.execute("SELECT cep FROM cidades WHERE cep = %s", (cli_cep,))
                    if not pg_cur.fetchone():
                        cli_cep = None
                        
                print(f"Inserindo cliente {cli_codigo} no PostgreSQL...")
                pg_cur.execute('''
                    INSERT INTO clientes (codigo, nome, cpf_cnpj, endereco, bairro, cep, fone, datacad)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (cli_codigo, cli_nome, cli_cpf_cnpj, cli_end, cli_bairro, cli_cep, cli_fone, cli_datacadastro))
            clientes_processados.add(cli_codigo)
            
        # Cadastra a parcela no PostgreSQL
        # Usamos RETURNING codigo para obter o ID gerado pelo sequence
        pg_cur.execute('''
            INSERT INTO parcelas (parcela, valor, vencimento, usuario)
            VALUES (%s, %s, %s, 1)
            RETURNING codigo
        ''', (rec_numero, rec_valor, rec_datavenc))
        
        parcela_gerada_codigo = pg_cur.fetchone()[0]
        
        # Faz o vinculo na tabela parcelas_clientes
        pg_cur.execute('''
            INSERT INTO parcelas_clientes (parcela, cliente)
            VALUES (%s, %s)
        ''', (parcela_gerada_codigo, cli_codigo))
        
        parcelas_inseridas += 1
        
    pg_conn.commit()
    print(f"Sincronização concluída! {parcelas_inseridas} parcelas foram lançadas no PostgreSQL (banco: control).")
    
    fb_conn.close()
    pg_conn.close()

if __name__ == '__main__':
    try:
        sync_data()
    except Exception as e:
        print(f"Ocorreu um erro durante a sincronização: {e}")
