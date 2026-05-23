from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import os
import psycopg2
import datetime

app = Flask(__name__)
app.secret_key = 'digipaper_secreto_inforbrasil_2026'
DB_PATH = 'contas_aberto.db'

# Senha de acesso criativa e segura para o sistema
APP_PASSWORD = "Digi*&098"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == APP_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = 'Senha incorreta. Tente novamente.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/api/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as total_clientes FROM clientes')
    total_clientes = cursor.fetchone()['total_clientes']
    
    cursor.execute('SELECT SUM(valor_parcela) as total_valor FROM contas')
    total_valor = cursor.fetchone()['total_valor']
    
    conn.close()
    return jsonify({
        'total_clientes': total_clientes,
        'total_valor': total_valor if total_valor else 0.0
    })

@app.route('/api/search')
def search():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
        
    query = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))
    offset = (page - 1) * limit
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if query:
        search_pattern = f"%{query}%"
        # Get total matching clients
        cursor.execute('''
            SELECT COUNT(DISTINCT c.id) as count
            FROM clientes c
            LEFT JOIN contas con ON con.cliente_id = c.id
            WHERE c.nome LIKE ? OR c.codigo LIKE ? OR con.numero LIKE ?
        ''', (search_pattern, search_pattern, search_pattern))
        total_matches = cursor.fetchone()['count']
        
        # Get paginated matching clients
        cursor.execute('''
            SELECT DISTINCT c.id, c.codigo, c.nome 
            FROM clientes c
            LEFT JOIN contas con ON con.cliente_id = c.id
            WHERE c.nome LIKE ? OR c.codigo LIKE ? OR con.numero LIKE ?
            ORDER BY c.nome
            LIMIT ? OFFSET ?
        ''', (search_pattern, search_pattern, search_pattern, limit, offset))
    else:
        cursor.execute('SELECT COUNT(*) as count FROM clientes')
        total_matches = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT id, codigo, nome 
            FROM clientes 
            ORDER BY nome
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        
    clientes_rows = cursor.fetchall()
    resultados = []
    
    for c_row in clientes_rows:
        cliente_id = c_row['id']
        cliente_dict = {
            'id': cliente_id,
            'codigo': c_row['codigo'],
            'nome': c_row['nome'],
            'contas': [],
            'total_aberto': 0.0
        }
        
        cursor.execute('''
            SELECT numero, venda, vencimento, situacao, valor_parcela
            FROM contas
            WHERE cliente_id = ?
            ORDER BY vencimento
        ''', (cliente_id,))
        contas_rows = cursor.fetchall()
        
        for con_row in contas_rows:
            conta_num = con_row['numero']
            conta_dict = {
                'numero': conta_num,
                'venda': con_row['venda'],
                'vencimento': con_row['vencimento'],
                'situacao': con_row['situacao'],
                'valor_parcela': con_row['valor_parcela'],
                'itens': []
            }
            cliente_dict['total_aberto'] += con_row['valor_parcela']
            
            cursor.execute('''
                SELECT codigo, descricao, qtd, unitario, total
                FROM itens
                WHERE conta_numero = ?
            ''', (conta_num,))
            itens_rows = cursor.fetchall()
            
            for it_row in itens_rows:
                conta_dict['itens'].append({
                    'codigo': it_row['codigo'],
                    'descricao': it_row['descricao'],
                    'qtd': it_row['qtd'],
                    'unitario': it_row['unitario'],
                    'total': it_row['total']
                })
                
            cliente_dict['contas'].append(conta_dict)
            
        resultados.append(cliente_dict)
        
    conn.close()
    
    # Calculate sum of ONLY the items currently on this page
    total_pagina = sum(c['total_aberto'] for c in resultados)
    
    return jsonify({
        'clientes': resultados,
        'total_matches': total_matches,
        'page': page,
        'total_pages': (total_matches + limit - 1) // limit,
        'total_pagina': total_pagina
    })

@app.route('/api/implantar/<int:cliente_codigo>', methods=['POST'])
def implantar(cliente_codigo):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    PG_HOST = os.environ.get('PG_HOST', '192.168.1.156')
    PG_USER = os.environ.get('PG_USER', 'postgres')
    PG_PASSWORD = os.environ.get('PG_PASSWORD', 'postgres')
    PG_DB = os.environ.get('PG_DB', 'control')

    try:
        sqlite_conn = get_db_connection()
        sqlite_cur = sqlite_conn.cursor()
        
        sqlite_cur.execute('''
            SELECT c.codigo, c.nome, 
                   co.numero, co.valor_parcela, co.vencimento
            FROM clientes c
            JOIN contas co ON co.cliente_id = c.id
            WHERE c.codigo = ? AND co.situacao != 'PAGA'
        ''', (str(cliente_codigo),))
        
        records = sqlite_cur.fetchall()
        sqlite_conn.close()
        
        if not records:
            return jsonify({'success': False, 'message': 'Nenhuma conta em aberto encontrada para este cliente no SQLite.'})

        pg_conn = psycopg2.connect(dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, host=PG_HOST)
        pg_cur = pg_conn.cursor()
        
        pg_cur.execute("SELECT get_usuario(1)")
        
        parcelas_inseridas = 0
        cliente_processado = False

        for row in records:
            cli_codigo = row['codigo']
            cli_nome = row['nome'] if row['nome'] else 'CLIENTE SEM NOME'
            cli_cpf_cnpj = ''
            cli_end = ''
            cli_bairro = ''
            cli_cep = None
            cli_fone = ''
            cli_datacadastro = datetime.date.today()
            
            rec_numero = row['numero']
            rec_valor = row['valor_parcela']
            rec_datavenc = row['vencimento']

            if not cliente_processado:
                if cli_cpf_cnpj:
                    pg_cur.execute("SELECT codigo FROM clientes WHERE cpf_cnpj = %s", (cli_cpf_cnpj,))
                else:
                    pg_cur.execute("SELECT codigo FROM clientes WHERE nome = %s", (cli_nome,))
                
                cliente_existente = pg_cur.fetchone()
                
                if cliente_existente:
                    cli_codigo_novo = cliente_existente[0]
                else:
                    if cli_cep:
                        pg_cur.execute("SELECT cep FROM cidades WHERE cep = %s", (cli_cep,))
                        if not pg_cur.fetchone():
                            cli_cep = None
                            
                    pg_cur.execute('''
                        INSERT INTO clientes (nome, cpf_cnpj, endereco, bairro, cep, fone, datacad)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING codigo
                    ''', (cli_nome, cli_cpf_cnpj, cli_end, cli_bairro, cli_cep, cli_fone, cli_datacadastro))
                    cli_codigo_novo = pg_cur.fetchone()[0]
                    
                cliente_processado = True
                
            pg_cur.execute("SELECT codigo FROM parcelas WHERE parcela = %s", (rec_numero,))
            if not pg_cur.fetchone():
                hoje = datetime.date.today()
                
                pg_cur.execute('''
                    INSERT INTO faturas (valor, data, usuario, cliente, cod_vendedor)
                    VALUES (%s, %s, 1, %s, 1)
                    RETURNING numero
                ''', (rec_valor, hoje, cli_codigo_novo))
                fatura_numero = pg_cur.fetchone()[0]
                
                pg_cur.execute('''
                    INSERT INTO parcelas (parcela, valor, vencimento, usuario)
                    VALUES (%s, %s, %s, 1)
                    RETURNING codigo
                ''', (rec_numero, rec_valor, rec_datavenc))
                parcela_gerada_codigo = pg_cur.fetchone()[0]
                
                pg_cur.execute('''
                    INSERT INTO faturas_destino (fatura, parcela)
                    VALUES (%s, %s)
                ''', (fatura_numero, parcela_gerada_codigo))
                
                pg_cur.execute('''
                    INSERT INTO parcelas_clientes (parcela, cliente)
                    VALUES (%s, %s)
                ''', (parcela_gerada_codigo, cli_codigo_novo))
                
                parcelas_inseridas += 1

        pg_conn.commit()
        return jsonify({'success': True, 'message': f'{parcelas_inseridas} parcelas importadas com sucesso!'})

    except Exception as e:
        if 'pg_conn' in locals():
            pg_conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if 'pg_cur' in locals(): pg_cur.close()
        if 'pg_conn' in locals(): pg_conn.close()

if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print("Banco de dados não encontrado. Rode 'python build_db.py' primeiro.")
    else:
        app.run(debug=True, port=5000)
