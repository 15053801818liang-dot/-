#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
@protocol YBLLMStreamDelegate <NSObject>
- (void)streamDidReceiveToken:(NSString *)token forSession:(NSString *)sessionId;
- (void)streamDidFinishForSession:(NSString *)sessionId;
- (void)streamDidFailWithError:(NSError *)error forSession:(NSString *)sessionId;
@end

@interface YBLLMMultiSessionStreamManager : NSObject
+ (instancetype)shared;
- (void)startStreamForSession:(NSString *)sessionId prompt:(NSString *)prompt delegate:(id<YBLLMStreamDelegate>)delegate;
- (void)cancelStreamForSession:(NSString *)sessionId;
- (void)resumeFromCheckpoint:(NSData *)checkpointData forSession:(NSString *)sessionId;
@property (nonatomic, readonly) NSArray<NSString *> *activeSessions;
@end
NS_ASSUME_NONNULL_END
