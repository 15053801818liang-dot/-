#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

typedef NS_ENUM(NSInteger, YBPromptEnvironment) {
    YBPromptEnvironmentDevelopment,
    YBPromptEnvironmentStaging,
    YBPromptEnvironmentRelease
};

@interface SystemPrompt : NSObject
+ (instancetype)shared;
- (NSString *)promptForEnvironment:(YBPromptEnvironment)environment;
- (void)setOverlay:(NSString *)overlay forEnvironment:(YBPromptEnvironment)environment;
@end

NS_ASSUME_NONNULL_END
