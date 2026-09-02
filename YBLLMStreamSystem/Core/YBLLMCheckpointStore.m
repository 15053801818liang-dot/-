#import "YBLLMCheckpointStore.h"

@interface YBLLMCheckpointStore ()
@property (nonatomic) dispatch_queue_t queue;
@property (nonatomic) NSMutableDictionary<NSString *, NSData *> *storage;
@end
@implementation YBLLMCheckpointStore
+ (instancetype)shared { static id value; static dispatch_once_t once; dispatch_once(&once, ^{ value = [[self alloc] initPrivate]; }); return value; }
- (instancetype)init { return [YBLLMCheckpointStore shared]; }
- (instancetype)initPrivate { if ((self = [super init])) { _queue = dispatch_queue_create("com.yb.llm.checkpoints", DISPATCH_QUEUE_CONCURRENT); _storage = [NSMutableDictionary dictionary]; } return self; }
- (BOOL)saveCheckpoint:(NSData *)checkpoint forSession:(NSString *)sessionId error:(NSError **)error {
    if (!sessionId.length) { if (error) *error = [NSError errorWithDomain:@"YBLLMCheckpointStore" code:1 userInfo:@{NSLocalizedDescriptionKey:@"Session identifier is empty"}]; return NO; }
    dispatch_barrier_sync(self.queue, ^{ self.storage[sessionId] = [checkpoint copy]; }); return YES;
}
- (NSData *)loadCheckpointForSession:(NSString *)sessionId error:(NSError **)error { __block NSData *data; dispatch_sync(self.queue, ^{ data = self.storage[sessionId]; }); return data; }
- (BOOL)deleteCheckpointForSession:(NSString *)sessionId error:(NSError **)error { dispatch_barrier_sync(self.queue, ^{ [self.storage removeObjectForKey:sessionId]; }); return YES; }
@end
