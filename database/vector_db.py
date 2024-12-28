import os
from datetime import datetime, timezone
from typing import List

from pinecone import Pinecone

from models.memory import Memory
#from utils.llm import embeddings

import tcvectordb
from tcvectordb.model.enum import FieldType, IndexType, MetricType, ReadConsistency
from tcvectordb.model.index import Index, VectorIndex, FilterIndex, HNSWParams
from tcvectordb.model.collection import UpdateQuery
from tcvectordb.model.document import Document, SearchParams, Filter


if os.getenv('PINECONE_API_KEY') is not None:
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY', ''))
    index = pc.Index(os.getenv('PINECONE_INDEX_NAME', ''))
else:
    index = None

'''
client = tcvectordb.VectorDBClient(
        url='http://lb-9zlfyvcb-e6owu0xtq2pl4i8h.clb.ap-beijing.tencentclb.com:30000', 
        username='root', key='EOaufC3nm7b1TJGVswxG1Z1YF1MmTZY0vBLhkVsK', 
        read_consistency=ReadConsistency.EVENTUAL_CONSISTENCY, 
        timeout=30)
db = client.create_database(database_name='db-test')
index = Index(
            FilterIndex(name='id', field_type=FieldType.String, index_type=IndexType.PRIMARY_KEY),
            VectorIndex(name='vector', dimension=3, index_type=IndexType.HNSW,
                        metric_type=MetricType.COSINE, params=HNSWParams(m=16, efconstruction=200)),
            FilterIndex(name='bookName', field_type=FieldType.String, index_type=IndexType.FILTER)               
        )        
# create a collection 
# 免费测试版实例，其分片 shard 只能为 1，副本 replicas 仅能为 0。        
coll = db.create_collection(
            name='book-vector',
            shard=1,
            replicas=0,
            description='this is a collection book vector',
            index=index
        )
'''

def _get_data(uid: str, memory_id: str, vector: List[float]):
    return {
        "id": f'{uid}-{memory_id}',
        "values": vector,
        'metadata': {
            'uid': uid,
            'memory_id': memory_id,
            'created_at': datetime.now(timezone.utc).timestamp() / 1000,  # TODO: check this
        }
    }


def upsert_vector(uid: str, memory: Memory, vector: List[float]):
    res = index.upsert(vectors=[_get_data(uid, memory.id, vector)], namespace="ns1")
    print('upsert_vector', res)


def upsert_vectors(
        uid: str, vectors: List[List[float]], memories: List[Memory]
):
    data = [
        _get_data(uid, memory.id, vector) for memory, vector in
        zip(memories, vectors)
    ]
    res = index.upsert(vectors=data, namespace="ns1")
    print('upsert_vectors', res)


def query_vectors(query: str, uid: str, starts_at: int = None, ends_at: int = None, k:int = 5) -> List[str]:
    filter_data = {'uid': uid}
    if starts_at is not None:
        filter_data['created_at'] = {'$gte': starts_at, '$lte': ends_at}

    # print('filter_data', filter_data)
    xq = embeddings.embed_query(query)
    xc = index.query(vector=xq, top_k=k, include_metadata=False, filter=filter_data, namespace="ns1")
    # print(xc)
    return [item['id'].replace(f'{uid}-', '') for item in xc['matches']]


def delete_vector(memory_id: str):
    index.delete(ids=[memory_id], namespace="ns1")
