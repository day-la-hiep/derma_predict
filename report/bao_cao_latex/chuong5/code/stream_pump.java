List<MapRecord<String,Object,Object>> records =
    redis.opsForStream().read(
        StreamReadOptions.empty().block(BLOCK).count(100),
        StreamOffset.create(key, ReadOffset.from(lastId)));
for (MapRecord<String,Object,Object> record : records) {
    lastId = record.getId().getValue();
    String event = String.valueOf(record.getValue().get("event"));
    emitter.send(SseEmitter.event().id(lastId).data(event));
}
