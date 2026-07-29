#import "SystemPrompt.h"

@interface SystemPrompt ()
@property (nonatomic) dispatch_queue_t queue;
@property (nonatomic) NSMutableDictionary<NSNumber *, NSString *> *overlays;
@end

@implementation SystemPrompt

+ (instancetype)shared {
    static SystemPrompt *instance;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{ instance = [[self alloc] initPrivate]; });
    return instance;
}

- (instancetype)init { return [SystemPrompt shared]; }

- (instancetype)initPrivate {
    if ((self = [super init])) {
        _queue = dispatch_queue_create("com.yb.llm.prompt", DISPATCH_QUEUE_CONCURRENT);
        _overlays = [NSMutableDictionary dictionary];
    }
    return self;
}

- (NSString *)promptForEnvironment:(YBPromptEnvironment)environment {
    __block NSString *overlay;
    dispatch_sync(self.queue, ^{ overlay = self.overlays[@(environment)]; });
    NSString *base = @"You are a helpful, accurate, and safe assistant.";
    return overlay.length ? [base stringByAppendingFormat:@"\n%@", overlay] : base;
}

- (void)setOverlay:(NSString *)overlay forEnvironment:(YBPromptEnvironment)environment {
    dispatch_barrier_sync(self.queue, ^{ self.overlays[@(environment)] = [overlay copy]; });
}
@end
