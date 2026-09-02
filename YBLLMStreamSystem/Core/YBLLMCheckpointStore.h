#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
@interface YBLLMCheckpointStore : NSObject
+ (instancetype)shared;
- (BOOL)saveCheckpoint:(NSData *)checkpoint forSession:(NSString *)sessionId error:(NSError **)error;
- (nullable NSData *)loadCheckpointForSession:(NSString *)sessionId error:(NSError **)error;
- (BOOL)deleteCheckpointForSession:(NSString *)sessionId error:(NSError **)error;
@end
NS_ASSUME_NONNULL_END
