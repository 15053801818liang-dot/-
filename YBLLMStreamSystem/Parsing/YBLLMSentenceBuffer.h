#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
@interface YBLLMSentenceBuffer : NSObject
@property (nonatomic, copy, readonly) NSString *visibleText;
- (void)appendToken:(NSString *)token;
- (void)undoLastSentence;
@end
NS_ASSUME_NONNULL_END
