"""Router admin danh mục loại thực thể / quan hệ của bước graph"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_document_graph_service, get_graph_schema_service
from app.dto.base.graph_schema import GraphEntityTypeDefinition, GraphRelationDefinition
from app.dto.common import ApiResponse
from app.dto.request.graph_schema import EntityTypeCreate, EntityTypeUpdate, RelationCreate, RelationUpdate
from app.services.document_graph_service import DocumentGraphService
from app.services.graph_schema_service import GraphSchemaService

router = APIRouter(prefix="/admin/graph-schema", tags=["admin-graph-schema"])

Schema = Annotated[GraphSchemaService, Depends(get_graph_schema_service)]
Graph = Annotated[DocumentGraphService, Depends(get_document_graph_service)]


@router.get("/entity-types", response_model=ApiResponse[list[GraphEntityTypeDefinition]], operation_id="listGraphEntityTypes")
async def list_entity_types(schema: Schema) -> ApiResponse[list[GraphEntityTypeDefinition]]:
    return ApiResponse(data=await asyncio.to_thread(schema.list_entity_types))


@router.post("/entity-types", response_model=ApiResponse[GraphEntityTypeDefinition], status_code=201, operation_id="createGraphEntityType")
async def create_entity_type(body: EntityTypeCreate, schema: Schema) -> ApiResponse[GraphEntityTypeDefinition]:
    return ApiResponse(data=await asyncio.to_thread(schema.create_entity_type, body))


@router.patch("/entity-types/{entity_type_id}", response_model=ApiResponse[GraphEntityTypeDefinition], operation_id="updateGraphEntityType")
async def update_entity_type(entity_type_id: str, body: EntityTypeUpdate, schema: Schema) -> ApiResponse[GraphEntityTypeDefinition]:
    return ApiResponse(data=await asyncio.to_thread(schema.update_entity_type, entity_type_id, body))


@router.delete("/entity-types/{entity_type_id}", status_code=204, operation_id="deleteGraphEntityType")
async def delete_entity_type(entity_type_id: str, schema: Schema) -> None:
    await asyncio.to_thread(schema.delete_entity_type, entity_type_id)


@router.get("/relations", response_model=ApiResponse[list[GraphRelationDefinition]], operation_id="listGraphRelations")
async def list_relations(schema: Schema) -> ApiResponse[list[GraphRelationDefinition]]:
    return ApiResponse(data=await asyncio.to_thread(schema.list_relations))


@router.post("/relations", response_model=ApiResponse[GraphRelationDefinition], status_code=201, operation_id="createGraphRelation")
async def create_relation(body: RelationCreate, schema: Schema) -> ApiResponse[GraphRelationDefinition]:
    return ApiResponse(data=await asyncio.to_thread(schema.create_relation, body))


@router.patch("/relations/{relation_id}", response_model=ApiResponse[GraphRelationDefinition], operation_id="updateGraphRelation")
async def update_relation(relation_id: str, body: RelationUpdate, schema: Schema) -> ApiResponse[GraphRelationDefinition]:
    return ApiResponse(data=await asyncio.to_thread(schema.update_relation, relation_id, body))


@router.delete("/relations/{relation_id}", status_code=204, operation_id="deleteGraphRelation")
async def delete_relation(relation_id: str, schema: Schema, graph: Graph) -> None:
    # Neo4j chưa cấu hình thì chưa có cạnh nào để xoá
    purge = graph.delete_relation_edges if graph.configured else (lambda _t: None)
    await asyncio.to_thread(schema.delete_relation, relation_id, purge)
