import os
import re
import json
import time
import numpy as np
import openai
from openai.embeddings_utils import get_embedding, cosine_similarity
from data.db_connection import graph

OPEN_API_KEY = os.getenv('OPEN_API_KEY',False)
openai.api_key = OPEN_API_KEY

def chunker(seq, size):
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))

def get_chunks(text,size):
    # Create questions for resource
    if len(text.split()) <= size:
        chunks = [text]
       
    else:
        words = text.split()
        chunks = []
        allchunks = [chunk for chunk in chunker(words,size) if len(chunk)>200]
        numchunks = len(allchunks)
           
        for chunk in allchunks:
            if len(chunk) > 200:
                chunk = ' '.join(chunk)
                chunks.append(chunk)

    return chunks


def get_answer_from_item(question,chunk,courseTitle,level):

    # Determine if question answer or explanation request

    prompt=f'''Use the following pieces of context if they help to answer the question at the end. 
        If you don't know the answer, just say that you don't know, don't try to make up an answer. 
        If the question is not relevant to the course you are teaching with the title {courseTitle}, just say that the question is not relevant to the course.
        Use at most five sentences and keep the answer as concise as possible.  
        Always say "thanks for asking!" at the end of the answer. 
        {chunk}
        Question: {question}
        Helpful Answer:'''

    messages = [
        {"role":'system',"content": f'''You are a friendly professor teaching a {level} level class and are answering a question from a student. If the answer contains any 
        equations, use LaTex with $$ as the delimiter for all equations and inline math.  Format your response as if you were the professor speaking directly to the student.'''},
        {"role":'user',"content":prompt}
    ]

    retries = 1
    success = False
    while not success and retries <= 3:
        try:
            response = openai.ChatCompletion.create(
                # model="gpt-3.5-turbo",
                model="gpt-4",
                messages=messages,
                temperature=0,
                # max_tokens=max_tokens,
                top_p=1,
                n=1,
                frequency_penalty=0,
                presence_penalty=0
                )
            success = True
        except Exception as e:
            wait = retries * 3
            time.sleep(wait)
            retries += 1

    
    response = response['choices'][0]['message']['content'].strip()
    pattern = r"```([\s\S]*?)```"
    response = re.sub(pattern, r"<code>\1</code>", response)

    return response


def embed(text):
    embedding = get_embedding(text,engine='text-embedding-ada-002')
    return embedding

def searchEmbeddings(question,items):
    qEmb = embed(question)
    sims = []
    allchunks = [] # chunk text
    allchunkIDs = [] # chunk ids
    refs = [] # item ids
    for item in items:
        # Get chunks and their embeddings
        # query to get itemChunk nodes with relationship to item
        query = '''MATCH (x:item)-[r:CHUNK_IN_ITEM]->(y:chunk) WHERE x.id = "{}" RETURN properties(y) as properties'''.format(item['id'])
        chunks = graph.query(query)
        embs = [chunk['embedding'] for chunk in chunks if 'embedding' in chunk.keys()]
        # embs = item.embeddings
        if len(embs) > 0:
            chunkIDs = [chunkNode['id'] for chunkNode in chunks if 'embedding' in chunkNode.keys()]
            chunks = [chunkNode['text'] for chunkNode in chunks if 'text' in chunkNode.keys() and chunkNode['text'] is not None]
            for i,emb in enumerate(embs):
                if type(emb) == list:
                    emb = [float(e) for e in emb]
                    sim = cosine_similarity(qEmb,emb)
                    sims.append(sim)
                    allchunks.append(chunks[i])
                    allchunkIDs.append(chunkIDs[i])
                    refs.append(item['id'])

    idxs = np.argsort(sims)[::-1]
    topsims = [sims[i] for i in idxs]
    topchunks = [allchunks[i] for i in idxs]
    toprefs = [refs[i] for i in idxs]
    topchunkIDs = [allchunkIDs[i] for i in idxs]

    return topchunks,toprefs,topchunkIDs

    prompt = f"""You are a teacher and someone has written the below lesson plan for you formatted in html.  
    You would like to make the following changes to the lesson 
    plan: {adjustLessonPlanInput}. Keeping the lesson plan formatted in html, make the requested changes
    and return the updated lesson plan still formatted in html. Do not include any additional text in your response.
    
    Here is the lesson plan to adjust: 
    {lessonPlanText}
    """

    messages = [
        {"role":"system","content":'''You are the teacher of a {} class called {} for students in grade {} and are preparing a 
         lesson plan. Format your response in html and do not use any headings larger 
         than h3'''.format(subject,courseName,grade)},
        {"role":"user","content":prompt}
    ]

    retries = 1
    success = False
    while not success and retries <= 3:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.2,
                # max_tokens=max_tokens,
                top_p=1,
                n=1,
                )
            success = True
        except Exception as e:
            wait = retries * 3
            time.sleep(wait)
            retries += 1

    response = response['choices'][0]['message']['content']
    # if body tags in response, keep only the body
    if '<body>' in response:
        response = response.split('<body>')[-1]
        response = response.split('</body>')[0]

    # remove '\n' from response
    print(response)
    response = response.replace('\n','')
    print(response)
        
    return response