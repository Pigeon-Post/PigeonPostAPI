import uuid
from datetime import datetime
from collections import defaultdict
from typing import List, Dict
from openai import OpenAI
from database.qdrant_db import QdrantDB
from config.config import Config
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue, Range

class RAG:
    def __init__(self):
        self.db = QdrantDB(Config.COLLECTION_NAME)
        self.openai = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.recent_chunks = []
        self.max_recent_chunks = 10
        self.session_memory = defaultdict(list)

    def _get_embedding(self, text: str) -> List[float]:
        try:
            response = self.openai.embeddings.create(
                model=Config.EMBEDDING_MODEL,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            raise Exception(f"Failed to generate embedding: {str(e)}")

    def add_chunk_to_recent(self, chunk: Dict[str, any]):
        self.recent_chunks.append(chunk)
        if len(self.recent_chunks) > self.max_recent_chunks:
            self.recent_chunks.pop(0)

    def _search_recent_chunks(self, course_title: str, lecture_title: str, 
                            current_date: datetime.date, segment_id: str = None, 
                            limit: int = 3) -> List[Dict]:
        results = [
            chunk for chunk in self.recent_chunks
            if chunk['course_title'] == course_title and 
               chunk['lecture_title'] == lecture_title and
               datetime.fromisoformat(chunk['timestamp']).date() == current_date and
               (segment_id is None or chunk.get('segment_id') == segment_id)
        ]
        return results[:limit]

    def add_lecture_chunk_to_db(self, chunk_data: dict) -> dict:
        try:
            embedding = self._get_embedding(chunk_data['content'])
            point_id = str(uuid.uuid4())
            
            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "course_title": chunk_data['course_title'],
                    "lecture_title": chunk_data['lecture_title'],
                    "text": chunk_data['content'],
                    "timestamp": chunk_data['timestamp'],
                    "chunk_number": chunk_data['chunk_number'],
                    "segment_id": chunk_data['segment_id']
                }
            )
            
            self.db.add_points([point])
            self.add_chunk_to_recent({
                "text": chunk_data['content'],
                "course_title": chunk_data['course_title'],
                "lecture_title": chunk_data['lecture_title'],
                "timestamp": chunk_data['timestamp'],
                "chunk_number": chunk_data['chunk_number'],
                "segment_id": chunk_data['segment_id']
            })
            
            return {"status": "success", "message": "Chunk added successfully"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to add chunk: {str(e)}"}

    def add_lecture_to_db(self, course_title: str, lecture_title: str, content: str) -> dict:
        try:
            chunks = self._chunk_text(content)
            points = []
            for position, chunk in chunks:
                embedding = self._get_embedding(chunk)
                point_id = str(uuid.uuid4())
                timestamp = datetime.now().isoformat()
                chunk_data = {
                    "course_title": course_title,
                    "lecture_title": lecture_title,
                    "text": chunk,
                    "position": position,
                    "timestamp": timestamp
                }
                points.append(PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=chunk_data
                ))
                self.add_chunk_to_recent(chunk_data)
            self.db.add_points(points)
            return {"status": "success", "message": "Lecture added successfully."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to add lecture content: {str(e)}"}

    def query(self, question: str, course_title: str, lecture_title: str, 
          segment_id: str = None, prefer_recent: bool = True, limit: int = 3) -> dict:
        try:
            current_date = datetime.now().date()
            session_key = f"{course_title}_{lecture_title}_{current_date}"
            recent_results = self._search_recent_chunks(
                course_title, lecture_title, current_date, segment_id, limit
            ) if prefer_recent else []

            if len(recent_results) < limit:
                query_embedding = self._get_embedding(question)
                filter_conditions = [
                    FieldCondition(key="course_title", match=MatchValue(value=course_title)),
                    FieldCondition(key="lecture_title", match=MatchValue(value=lecture_title))
                ]
                
                if segment_id:
                    filter_conditions.append(
                        FieldCondition(key="segment_id", match=MatchValue(value=segment_id))
                    )
                
                db_results = self.db.search(
                    query_vector=query_embedding,  # Changed from vector to query_vector
                    filter=Filter(must=filter_conditions),
                    limit=limit - len(recent_results)
                )
                
                # Filter results by date in memory
                current_date_str = current_date.isoformat()
                db_parsed = [
                    {
                        "text": hit.payload['text'],
                        "course_title": hit.payload['course_title'],
                        "lecture_title": hit.payload['lecture_title'],
                        "timestamp": hit.payload['timestamp'],
                        "chunk_number": hit.payload.get('chunk_number'),
                        "segment_id": hit.payload.get('segment_id')
                    } 
                    for hit in db_results
                    if hit.payload['timestamp'].split('T')[0] == current_date_str
                ]
                combined_results = recent_results + db_parsed
            else:
                combined_results = recent_results

            if not combined_results:
                response = self._generate_gpt_response(question)
                return {
                    "answer": response,
                    "sources": [],
                    "metadata": [],
                    "from_gpt": True
                }

            combined_results.sort(key=lambda x: x['timestamp'])
            contexts = [r['text'] for r in combined_results]
            response = self._generate_gpt_response_with_contexts(question, contexts)

            if response not in self.session_memory[session_key]:
                self.session_memory[session_key].append(response)

            return {
                "answer": response,
                "sources": contexts,
                "metadata": [{
                    "timestamp": r['timestamp'],
                    "chunk_number": r.get('chunk_number'),
                    "segment_id": r.get('segment_id')
                } for r in combined_results],
                "from_gpt": False
            }
        except Exception as e:
            return {"status": "error", "message": f"Query failed: {str(e)}"}

    def _generate_gpt_response(self, question: str) -> str:
        messages = [
            {"role": "system", "content": "You are a helpful teaching assistant."},
            {"role": "user", "content": question}
        ]
        response = self.openai.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content

    def _generate_gpt_response_with_contexts(self, question: str, contexts: List[str]) -> str:
        system_message = """You are an AI assistant specifically trained to answer questions based ONLY on the provided lecture content. 
        Your knowledge is limited to the information given in the context. Follow these rules strictly:
        1. Only use information explicitly stated in the provided context.
        2. If the context doesn't contain relevant information to answer the question, say "I don't have enough information to answer that question based on the provided lecture content."
        3. Do not use any external knowledge or make assumptions beyond what's in the context.
        4. If asked about topics not covered in the context, state that the lecture content doesn't cover that topic.
        5. Be precise and concise in your answers, citing specific parts of the context when possible.
        6. If the question is ambiguous or unclear based on the context, ask for clarification.
        7. Never claim to know more than what's provided in the context.
        8. If the context contains conflicting information, point out the inconsistency without resolving it.
        Remember, your role is to interpret and relay the information from the lecture content, not to provide additional knowledge or opinions."""

        context_message = "Context from lecture content:\n" + "\n".join(contexts)

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": context_message},
            {"role": "user",
             "content": f"Question: {question}\nAnswer only based on the above context, following the rules provided."}
        ]

        response = self.openai.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=messages,
            temperature=0.3  # Lower temperature for more deterministic outputs
        )
        return response.choices[0].message.content

    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[tuple]:
        words = text.split()
        chunks = []
        current_chunks = []
        current_size = 0
        position = 0

        for word in words:
            current_chunks.append(word)
            current_size += len(word) + 1

            if current_size >= chunk_size:
                chunks.append((position, " ".join(current_chunks)))
                current_chunks = []
                current_size = 0
                position += 1

        if current_chunks:
            chunks.append((position, " ".join(current_chunks)))

        return chunks
    
    def get_complete_lecture(self, course_title: str, lecture_title: str) -> dict:
        try:
            # Get all content for this lecture - Remove collection_name parameter
            results = self.db.search_by_metadata(
                filter=Filter(
                    must=[
                        FieldCondition(key="course_title", match=MatchValue(value=course_title)),
                        FieldCondition(key="lecture_title", match=MatchValue(value=lecture_title))
                    ]
                ),
                limit=100  # Adjust based on your needs
            )
            
            if not results:
                return {
                    "status": "error",
                    "message": "No content found for this lecture"
                }

            # Sort by timestamp and chunk number
            sorted_results = sorted(
                results,
                key=lambda x: (
                    datetime.fromisoformat(x.payload['timestamp']),
                    x.payload.get('chunk_number', 0)
                )
            )

            # Organize content by segments
            segments = {}
            for result in sorted_results:
                segment_id = result.payload.get('segment_id', 'default')
                if segment_id not in segments:
                    segments[segment_id] = {
                        'content': [],
                        'timestamp': result.payload['timestamp'],
                        'chunk_count': 0
                    }
                segments[segment_id]['content'].append(result.payload['text'])
                segments[segment_id]['chunk_count'] += 1

            # Create a formatted version of the complete lecture
            formatted_content = []
            for segment_id, data in segments.items():
                formatted_content.append(f"\n--- Segment {segment_id} ---")
                formatted_content.extend(data['content'])

            return {
                "status": "success",
                "lecture_info": {
                    "course_title": course_title,
                    "lecture_title": lecture_title,
                    "total_segments": len(segments),
                    "total_chunks": sum(s['chunk_count'] for s in segments.values())
                },
                "complete_content": "\n".join(formatted_content),
                "segments": segments
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to retrieve lecture content: {str(e)}"}

# Add to QdrantDB class:
def search_by_metadata(self, filter: Filter, limit: int = 100):
    return self.client.scroll(
        collection_name=self.collection_name,
        scroll_filter=filter,
        limit=limit
    )[0]