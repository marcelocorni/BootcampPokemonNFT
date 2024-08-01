import requests
import json
from web3 import Web3
import os
from solcx import compile_standard, install_solc, get_installed_solc_versions, get_installable_solc_versions, set_solc_version
import streamlit as st

# Função para garantir que a versão necessária do solc está instalada
def ensure_solc_installed(version='0.8.26'):
    installed_versions = get_installed_solc_versions()
    installed_versions_str = [str(ver) for ver in installed_versions]

    if version not in installed_versions_str:
        installable_versions = get_installable_solc_versions()
        if version in installable_versions:
            st.info(f"Instalando a versão {version} do solc...")
            install_solc(version)
            st.success(f"Versão {version} do solc instalada com sucesso.")
        else:
            available_version = max(installable_versions)
            st.warning(f"A versão {version} do solc não está disponível. Instalando a versão {available_version} em vez disso.")
            install_solc(available_version)
            set_solc_version(available_version)
            st.success(f"Versão {available_version} do solc instalada com sucesso.")
    else:
        set_solc_version(version)

# Garantir que a versão específica do compilador Solidity está instalada
try:
    ensure_solc_installed('0.8.26')
except Exception as e:
    st.error(f"Erro ao garantir a instalação do solc: {e}")
    raise

# Configurar a conexão com o nó local do Ganache
w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))

# Função para compilar o contrato
def compile_contract(files):
    sources = {}
    for path, content in files.items():
        normalized_path = os.path.normpath(path).replace("\\", "/")
        sources[normalized_path] = {'content': content}

    try:
        compiled_sol = compile_standard({
            'language': 'Solidity',
            'sources': sources,
            'settings': {
                'outputSelection': {
                    '*': {
                        '*': ['abi', 'evm.bytecode', 'metadata']
                    }
                }
            }
        }, allow_paths='./node_modules')
    except Exception as e:
        st.error(f"Erro durante a compilação: {e}")
        raise

    if not compiled_sol.get('contracts'):
        st.error(f"Compilação falhou. Detalhes: {compiled_sol}")
        raise ValueError("Compilação falhou: Nenhum contrato compilado")

    # Salvar contratos compilados no estado da sessão
    st.session_state['compiled_contracts'] = compiled_sol['contracts']

    # Procurar pelo contrato concreto a ser implantado
    for file_name, contracts in compiled_sol['contracts'].items():
        for contract_name, contract_data in contracts.items():
            abi = contract_data.get('abi')
            bytecode_info = contract_data.get('evm', {}).get('bytecode', {})
            bytecode = bytecode_info.get('object')
            if bytecode is None or bytecode == "":
                st.error(f"Bytecode não gerado para o contrato: {contract_name}")
                continue
            st.write(f"Verificando contrato: {contract_name} com bytecode de tamanho {len(bytecode)}")
            if abi and bytecode and len(bytecode) > 0:  # Verifica se o bytecode é válido
                st.write(f"Contrato encontrado para implantação: {contract_name}")
                return abi, bytecode, contract_name

    raise ValueError("Compilação falhou: Nenhum contrato concreto encontrado")

# Função para listar arquivos em um diretório IPFS
def list_files_in_directory(directory_hash):
    response = requests.post(f'http://127.0.0.1:5001/api/v0/ls', params={'arg': directory_hash})
    return response.json()

# Função para obter a lista de objetos Pokémon
def get_pokemon_list(directory_hash):
    files = list_files_in_directory(directory_hash)['Objects'][0]['Links']

    pokemon_list = []
    for file in files:
        file_hash = file['Hash']
        file_name = file['Name'].rsplit('.', 1)[0]  # Remover a extensão do arquivo
        file_link = f"https://ipfs.io/ipfs/{file_hash}"
        pokemon = {
            'name': file_name,
            'level': 1,
            'img': file_link
        }
        pokemon_list.append(pokemon)

    return pokemon_list

# Interface Streamlit
st.title("Deploy de Contratos Solidity")

# Upload dos arquivos .sol
uploaded_files = st.file_uploader("Escolha os arquivos Solidity (.sol)", type=["sol"], accept_multiple_files=True)

if uploaded_files:
    files = {}
    for uploaded_file in uploaded_files:
        file_path = os.path.join("contracts", uploaded_file.name)
        dir_path = os.path.dirname(file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        files[file_path] = uploaded_file.getbuffer().tobytes().decode('utf-8')
    st.success("Arquivos carregados com sucesso")

    # Seleção da carteira
    accounts = w3.eth.accounts
    selected_account = st.selectbox("Selecione a conta para o deploy", accounts)

    contract_address = None
    abi = None

    # Compilar e fazer o deploy do contrato
    if st.button("Compilar e Deploy"):
        with st.spinner("Compilando o contrato..."):
            try:
                abi, bytecode, contract_name = compile_contract(files)
                st.success("Contrato compilado com sucesso")
                # Deploy do contrato
                contract = w3.eth.contract(abi=abi, bytecode=bytecode)
                tx_hash = contract.constructor().transact({'from': selected_account})
                tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                contract_address = tx_receipt.contractAddress
                st.success(f"Contrato {contract_name} implantado com sucesso: {contract_address}")
                st.session_state['contract_address'] = contract_address
                st.session_state['abi'] = abi
            except Exception as e:
                st.error(f"Erro ao compilar e implantar o contrato: {e}")
                st.error(f"Detalhes: {str(e)}")

# Exibir contratos compilados salvos no estado da sessão
compiled_contracts = st.session_state.get('compiled_contracts', None)
if compiled_contracts:
    with st.expander("Contratos compilados"):
        st.json(compiled_contracts)

# Interação com o contrato implantado
contract_address = st.session_state.get('contract_address', None)
abi = st.session_state.get('abi', None)

if contract_address and abi:
    st.subheader("Interagir com o contrato implantado")

    contract = w3.eth.contract(address=contract_address, abi=abi)

    # Chamar createNewPokemon para cada Pokémon na lista
    if st.button("Criar Pokémons no Contrato"):
        pokemon_list = get_pokemon_list("QmZe4T9QfrZ2v467TbV8Y7Vw6YD6yznStxX8sRdAPGxdcK")
        for pokemon in pokemon_list:
            try:
                tx_hash = contract.functions.createNewPokemon(pokemon['name'], selected_account, pokemon['img']).transact({'from': selected_account})
                tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                st.success(f"Pokémon {pokemon['name']} criado com sucesso, hash da transação: {tx_receipt.transactionHash.hex()}")
            except Exception as e:
                st.error(f"Erro ao criar Pokémon {pokemon['name']}: {e}")

# Iniciar a aplicação Streamlit
if __name__ == "__main__":
    st.write("Deploy e Interação com Contratos Solidity")
