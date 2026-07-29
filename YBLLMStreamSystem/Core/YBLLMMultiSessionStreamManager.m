#import "YBLLMMultiSessionStreamManager.h"

@interface YBLLMStreamContext : NSObject
@property (nonatomic) id<YBLLMStreamDelegate> delegate;
@property (atomic, getter=isCancelled) BOOL cancelled;
@end
@implementation YBLLMStreamContext @end

@interface YBLLMMultiSessionStreamManager ()
@property (nonatomic) dispatch_queue_t stateQueue;
@property (nonatomic) NSMutableDictionary<NSString *, YBLLMStreamContext *> *contexts;
@end

@implementation YBLLMMultiSessionStreamManager
+ (instancetype)shared {
    static id instance; static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{ instance = [[self alloc] initPrivate]; });
    return instance;
}
- (instancetype)init { return [YBLLMMultiSessionStreamManager shared]; }
- (instancetype)initPrivate {
    if ((self = [super init])) {
        _stateQueue = dispatch_queue_create("com.yb.llm.stream-state", DISPATCH_QUEUE_SERIAL);
        _contexts = [NSMutableDictionary dictionary];
    }
    return self;
}
- (void)startStreamForSession:(NSString *)sessionId prompt:(NSString *)prompt delegate:(id<YBLLMStreamDelegate>)delegate {
    if (!sessionId.length || !delegate) return;
    [self cancelStreamForSession:sessionId];
    YBLLMStreamContext *context = [YBLLMStreamContext new];
    context.delegate = delegate;
    dispatch_sync(self.stateQueue, ^{ self.contexts[sessionId] = context; });

    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSArray<NSString *> *tokens = @[@"Hello", @" world", @"!", @" This", @" is", @" a", @" simulated", @" stream."];
        for (NSString *token in tokens) {
            if (context.isCancelled) return;
            dispatch_async(dispatch_get_main_queue(), ^{
                if (!context.isCancelled) [context.delegate streamDidReceiveToken:token forSession:sessionId];
            });
            [NSThread sleepForTimeInterval:0.1];
        }
        if (context.isCancelled) return;
        dispatch_sync(self.stateQueue, ^{ if (self.contexts[sessionId] == context) [self.contexts removeObjectForKey:sessionId]; });
        dispatch_async(dispatch_get_main_queue(), ^{ [context.delegate streamDidFinishForSession:sessionId]; });
    });
}
- (void)cancelStreamForSession:(NSString *)sessionId {
    dispatch_sync(self.stateQueue, ^{
        self.contexts[sessionId].cancelled = YES;
        [self.contexts removeObjectForKey:sessionId];
    });
}
- (void)resumeFromCheckpoint:(NSData *)checkpointData forSession:(NSString *)sessionId {
    __block id<YBLLMStreamDelegate> delegate;
    dispatch_sync(self.stateQueue, ^{ delegate = self.contexts[sessionId].delegate; });
    if (!delegate) return;
    NSString *prompt = [[NSString alloc] initWithData:checkpointData encoding:NSUTF8StringEncoding] ?: @"Resumed prompt";
    [self startStreamForSession:sessionId prompt:prompt delegate:delegate];
}
- (NSArray<NSString *> *)activeSessions {
    __block NSArray *sessions;
    dispatch_sync(self.stateQueue, ^{ sessions = [self.contexts.allKeys sortedArrayUsingSelector:@selector(compare:)]; });
    return sessions;
}
@end
