
from enum import Enum
from os import getenv
from typing import List, Optional

import strawberry
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from neo4j import GraphDatabase
from strawberry.asgi import GraphQL

load_dotenv()

NEO4J_URI = "neo4j+s://b3ae5671.databases.neo4j.io"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "shjNiQeFKr04HdXP0ADJUAtj_HZv7aTKrTdDjQh9vH8"


def _and(cur_filter, new_filter):
    if not cur_filter:
        return f"WHERE {new_filter} "
    return f"AND {new_filter} "


@strawberry.enum
class AnswerType(Enum):
    string = "String"
    bool = "Bool"
    float = "Float"
    # Unsure of the status of these - 2022-11-20:
    int = "Int"
    list = "List"
    label = "Label"
    date = "Date"


@strawberry.type
class Answer:
    uuid: str
    answer: str
    type: AnswerType
    createdAt: str
    updatedAt: str

    @classmethod
    def marshal(cls, obj) -> "Answer":
        return cls(
            uuid=obj['uuid'],
            answer=obj['answer'],
            type=obj['type'],
            createdAt=obj['created_at'],
            updatedAt=obj['updated_at']
        )


@strawberry.input
class SaveAnswerInput:
    answer: str
    questionUuid: str

    # TODO: Potentially refactor away from using this,
    # because the backend could look these up - 2022-11-20:
    type: AnswerType

    def to_dict(self):
        return {
            "answer": self.answer,
            "type": self.type.value,
            "questionUuid": self.questionUuid,
        }


@strawberry.input
class SaveAnswersInput:
    applicationUuid: str
    answers: List[SaveAnswerInput]

    def serialize(self):
        return [answer.to_dict() for answer in self.answers]


@strawberry.type
class Question:
    uuid: str
    sectionUuid: str
    order: str
    type: str
    questionString: str
    role: str
    answer: Optional[Answer]

    @classmethod
    def marshal(cls, question, answer=None) -> "Question":
        answer = answer if answer is None else Answer.marshal(answer)
        return cls(
            uuid=question['uuid'],
            sectionUuid=question['section_uuid'],
            order=question['order'],
            type=question['type'],
            questionString=question['question_string'],
            role=question['role'],
            answer=answer
        )


@strawberry.type
class Application:
    uuid: str
    name: str
    version: str
    createdAt: str
    updatedAt: str
    questions: List[Question]

    @classmethod
    def marshal(cls, application) -> "Application":

        questions = application.get('questions')
        print("Questions:", questions)
        questions = questions if questions else []
        print("Application_Questions", questions)

        return cls(
            uuid=application['uuid'],
            name=application['name'],
            version=application['version'],
            createdAt=application['created_at'],
            updatedAt=application['updated_at'],
            questions=[
                Question.marshal(
                    question.get('question'), question.get('answer')
                )
                for question in questions
            ]
        )


@strawberry.type
class ApplicantForm:
    uuid: str
    name: str
    createdAt: str
    updatedAt: str
    questions: List[Question]

    @classmethod
    def marshal(cls, applicant) -> "ApplicantForm":
        questions = applicant.get('questions')
        print("Questions:", questions)
        questions = questions if questions else []
        print("Applicant_Questions", questions)
        return cls(
            uuid=applicant['uuid'],
            name=applicant['name'],
            createdAt=applicant['created_at'],
            updatedAt=applicant['updated_at'],
            questions=[
                Question.marshal(
                    question.get('question'), question.get('answer')
                )
                for question in questions
            ]
        )


@strawberry.type
class Query:
    @strawberry.field()
    def applications(self) -> List[Application]:
        with graph.session() as session:
            query = """
                MATCH (a:Application) RETURN a
            """
            rows = session.run(query).data()
        return [
            Application.marshal(
                row['a']
            ) for row in rows
        ]

    @strawberry.field()
    def applicantForms(self) -> List[ApplicantForm]:
        with graph.session() as session:
            query = """
                MATCH (a:ApplicantForm)
                MATCH (ans:Answer)<-[r:HAS_ANSWER]-(a)
                MATCH (q:Question) where q.order="101"
                MATCH (q)-[r1:HAS_ANSWER]-(ans)--(a)
                SET a.name = ans.answer
                RETURN a
            """
            rows = session.run(query).data()
        return [
            ApplicantForm.marshal(
                row['a']
            ) for row in rows
        ]

    @strawberry.field()
    def getQuestions(self) -> List[Question]:
        with graph.session() as session:
            query = """
                MATCH (q:Question)
                RETURN q
            """
            rows = session.run(query).data()
        return [
            Question.marshal(
                row['q']
            ) for row in rows
        ]

    @strawberry.field()
    def getUserQuestions(self) -> List[Question]:
        with graph.session() as session:
            query = """
                match (a:Application)--(q:Question)
                WHERE q.role = "User"
                RETURN q
            """
            rows = session.run(query).data()
        return [
            Question.marshal(
                row['q']
            ) for row in rows
        ]

    @strawberry.field()
    def getAppeaserQuestions(self) -> List[Question]:
        with graph.session() as session:
            query = """
                MATCH (q:Question)
                WHERE q.role = "User" OR q.role = "Appeaser"
                RETURN q
            """
            rows = session.run(query).data()
        return [
            Question.marshal(
                row['q']
            ) for row in rows
        ]

    @strawberry.field()
    def getManagerQuestions(self) -> List[Question]:
        with graph.session() as session:
            query = """
                MATCH (q:Question)
                WHERE q.role = "User" OR q.role = "Appeaser"
                OR q.role = "Manager"
                RETURN q
            """
            rows = session.run(query).data()
        return [
            Question.marshal(
                row['q']
            ) for row in rows
        ]

    @strawberry.field()
    def getApplicantWithQuestion(
        self,
        applicantUuid: str
    ) -> ApplicantForm:

        ans_query = f"""
            MATCH
                (app:ApplicantForm {{uuid: '{applicantUuid}'}})-->
                (ans:Answer)<-[qa:HAS_ANSWER]-(q:Question)
            RETURN app, q, qa, ans
        """

        no_ans_query = f"""
            MATCH
                (app:ApplicantForm {{uuid: '{applicantUuid}'}})-->
                (q:Question)
            WHERE NOT
                (q)-[:HAS_ANSWER
                    {{has_ApplicantForm_uuid: '{applicantUuid}'}}
                ]->()
            RETURN app, q
        """
        with graph.session() as session:
            ans_rows = list()
            for record in session.run(ans_query):
                row = dict(record)
                ans_rows.append(row)
            no_ans_rows = list()
            for record in session.run(no_ans_query):
                row = dict(record)
                no_ans_rows.append(row)

        if ans_rows:
            app = dict(ans_rows[0]['app'])
            app['questions'] = list()
        if no_ans_rows:
            app = dict(no_ans_rows[0]['app'])
            app['questions'] = list()

        for row in ans_rows:
            app['questions'].append(
                {
                    "question": dict(row['q']),
                    "answer": dict(row['ans'])
                }
            )
        for row in no_ans_rows:
            app['questions'].append({"question": dict(row['q'])})
        return ApplicantForm.marshal(app)


@strawberry.type
class Mutation:
    @strawberry.mutation()
    def saveAnswers(
        self, data: SaveAnswersInput
    ) -> Optional[Question]:

        applicationUuid = data.applicationUuid

        with graph.session() as session:
            query = f"""
                UNWIND $answers as answer
                MATCH (q:Question),(f:ApplicantForm)
                WHERE q.uuid= answer.questionUuid
                AND f.uuid = '{applicationUuid}'
                MERGE
                    (q)-[r:HAS_ANSWER {{
                        has_application_uuid: '{applicationUuid}'
                    }}]->(a:Answer)
                MERGE
                    (f)-[m:HAS_ANSWER]->(a)
                ON CREATE SET
                    a.uuid = apoc.create.uuid(),
                    a.type = answer.type,
                    a.answer = answer.answer,
                    a.created_at = datetime({{epochmillis:timestamp()}}),
                    a.updated_at = datetime({{epochmillis:timestamp()}}),
                    r.uuid = apoc.create.uuid(),
                    r.has_application_uuid = '{applicationUuid}',
                    r.created_at = datetime({{epochmillis:timestamp()}}),
                    r.updated_at = datetime({{epochmillis:timestamp()}})
                ON MATCH SET
                    a.type = answer.type,
                    a.answer = answer.answer,
                    a.updated_at = datetime({{epochmillis:timestamp()}}),
                    r.updated_at = datetime({{epochmillis:timestamp()}})
                RETURN q, a, r
            """
            session.run(query, answers=data.serialize())
        return None

    @strawberry.mutation()
    def createQuestion(
        self, applicationUuid: str, questionString: str, type: str,
        sectionUuid: str, role: str
            ) -> Optional[Question]:

        with graph.session() as session:
            max_query = f"""
                MATCH (q:Question)
                WHERE q.section_uuid = '{sectionUuid}'
                RETURN max(toInteger(q.order))+1 as order
            """
            orderRec = session.run(max_query).data()
            y = [x['order'] for x in orderRec]
            order = y[0]
            query = f"""
                    MATCH (a:Application) where a.uuid =  '{applicationUuid}'
                    CREATE (q:Question) SET
                    q.question_string = '{questionString}',
                    q.type = '{type}',
                    q.order = '{order}',
                    q.section_uuid = '{sectionUuid}',
                    q.role ='{role}',
                    q.uuid = apoc.create.uuid()
                    MERGE (a)-[r:HAS_QUESTION]->(q)
                    RETURN q
                """
            row = session.run(query).single()
        return Question.marshal(row['q'])

    @strawberry.mutation()
    def submitApplicantForm(
        self, uuid: str, name: str
    ) -> Optional[ApplicantForm]:

        with graph.session() as session:
            query = f"""
                    CREATE (a:ApplicantForm) SET
                    a.uuid = '{uuid}',
                    a.created_at = datetime({{epochmillis:timestamp()}}),
                    a.updated_at = datetime({{epochmillis:timestamp()}}),
                    a.name = '{name}'

                    return a
                """
            row = session.run(query).single()
        return ApplicantForm.marshal(row['a'])

    @strawberry.mutation
    def sendMessage(
                self, data: str
            ) -> str:
        return "Hello World"


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_app = GraphQL(schema)
graph = GraphDatabase.driver(
    NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
)

origins = ["FE_APP_URLS", "http://localhost:3000", "http://frontend:3000",           "https://sst-insurance-neo4j-frontend.azurewebsites.net", "https://40.76.233.70"]


def create_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
    CORSMiddleware,
    allow_headers=["*"],
    allow_methods=["*"],
    allow_credentials=True,
    allow_origins=origins
    )

    app.middleware("http")
    def my_middleware(request: Request, call_next):
        response = call_next(request)
        return response

    app.add_route("/graphql", graphql_app)
    return app


app = create_app()
