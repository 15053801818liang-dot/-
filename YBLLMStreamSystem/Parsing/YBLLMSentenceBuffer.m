#import "YBLLMSentenceBuffer.h"
@interface YBLLMSentenceBuffer ()
@property (nonatomic) NSMutableArray<NSString *> *sentences;
@property (nonatomic) NSMutableString *current;
@end
@implementation YBLLMSentenceBuffer
- (instancetype)init { if ((self = [super init])) { _sentences = [NSMutableArray array]; _current = [NSMutableString string]; } return self; }
- (void)appendToken:(NSString *)token {
    [self.current appendString:token];
    NSCharacterSet *terminators = [NSCharacterSet characterSetWithCharactersInString:@"。！？.!?"];
    while (YES) {
        NSRange range = [self.current rangeOfCharacterFromSet:terminators];
        if (range.location == NSNotFound) break;
        [self.sentences addObject:[self.current substringToIndex:NSMaxRange(range)]];
        [self.current deleteCharactersInRange:NSMakeRange(0, NSMaxRange(range))];
    }
}
- (NSString *)visibleText { return [[self.sentences componentsJoinedByString:@""] stringByAppendingString:self.current]; }
- (void)undoLastSentence { if (self.sentences.count) [self.sentences removeLastObject]; }
@end
