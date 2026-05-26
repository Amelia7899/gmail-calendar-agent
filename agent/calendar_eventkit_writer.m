#import <Foundation/Foundation.h>
#import <EventKit/EventKit.h>
#import <dispatch/dispatch.h>

static void PrintError(NSString *message) {
    fprintf(stderr, "%s\n", [message UTF8String]);
}

static int FinishWithError(NSString *message, NSString *resultPath, int code) {
    PrintError(message);

    if (resultPath.length) {
        NSString *result = [NSString stringWithFormat:@"ERROR\n%@", message];
        [result writeToFile:resultPath atomically:YES encoding:NSUTF8StringEncoding error:nil];
    }

    return code;
}

static int FinishWithSuccess(NSString *identifier, NSString *resultPath) {
    NSString *safeIdentifier = identifier ?: @"";
    printf("%s\n", [safeIdentifier UTF8String]);

    if (resultPath.length) {
        NSString *result = [NSString stringWithFormat:@"OK\n%@", safeIdentifier];
        [result writeToFile:resultPath atomically:YES encoding:NSUTF8StringEncoding error:nil];
    }

    return 0;
}

static NSString *ArgumentAt(int argc, const char *argv[], int index) {
    if (index >= argc) {
        return @"";
    }

    return [NSString stringWithUTF8String:argv[index]];
}

static NSDate *ParseCalendarDate(NSString *dateText, NSString *timeText) {
    NSDateFormatter *formatter = [[NSDateFormatter alloc] init];
    formatter.locale = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
    formatter.dateFormat = @"yyyy-MM-dd HH:mm";
    return [formatter dateFromString:[NSString stringWithFormat:@"%@ %@", dateText, timeText]];
}

static BOOL RequestCalendarAccess(EKEventStore *store, NSString *resultPath) {
    EKAuthorizationStatus status = [EKEventStore authorizationStatusForEntityType:EKEntityTypeEvent];

    if (status == EKAuthorizationStatusFullAccess || status == EKAuthorizationStatusAuthorized) {
        return YES;
    }

    if (status == EKAuthorizationStatusDenied || status == EKAuthorizationStatusRestricted) {
        FinishWithError(
            @"Calendar access is denied. Enable calendar access in System Settings > Privacy & Security > Calendars, then try again.",
            resultPath,
            66
        );
        return NO;
    }

    __block BOOL granted = NO;
    __block NSError *requestError = nil;
    dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);

    if (@available(macOS 14.0, *)) {
        [store requestFullAccessToEventsWithCompletion:^(BOOL accessGranted, NSError *error) {
            granted = accessGranted;
            requestError = error;
            dispatch_semaphore_signal(semaphore);
        }];
    } else {
        [store requestAccessToEntityType:EKEntityTypeEvent completion:^(BOOL accessGranted, NSError *error) {
            granted = accessGranted;
            requestError = error;
            dispatch_semaphore_signal(semaphore);
        }];
    }

    dispatch_semaphore_wait(semaphore, DISPATCH_TIME_FOREVER);

    if (!granted) {
        if (requestError) {
            FinishWithError(
                [NSString stringWithFormat:@"Calendar access failed: %@", requestError.localizedDescription],
                resultPath,
                66
            );
        } else {
            FinishWithError(
                @"Calendar access was not granted. If no prompt appears, open System Settings > Privacy & Security > Calendars and allow Gmail Calendar Agent Calendar Writer.",
                resultPath,
                66
            );
        }
        return NO;
    }

    return YES;
}

static EKSource *PreferredCalendarSource(EKEventStore *store) {
    EKCalendar *defaultCalendar = [store defaultCalendarForNewEvents];
    if (defaultCalendar.source) {
        return defaultCalendar.source;
    }

    for (EKSource *source in store.sources) {
        if (source.sourceType == EKSourceTypeLocal) {
            return source;
        }
    }

    return store.sources.firstObject;
}

static EKCalendar *FindOrCreateCalendar(EKEventStore *store, NSString *calendarName) {
    for (EKCalendar *calendar in [store calendarsForEntityType:EKEntityTypeEvent]) {
        if ([calendar.title isEqualToString:calendarName]) {
            return calendar;
        }
    }

    EKSource *source = PreferredCalendarSource(store);
    if (!source) {
        return nil;
    }

    EKCalendar *calendar = [EKCalendar calendarForEntityType:EKEntityTypeEvent eventStore:store];
    calendar.title = calendarName;
    calendar.source = source;

    NSError *error = nil;
    if (![store saveCalendar:calendar commit:YES error:&error]) {
        return nil;
    }

    return calendar;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc == 1) {
            EKEventStore *store = [[EKEventStore alloc] init];
            if (!RequestCalendarAccess(store, @"")) {
                return 66;
            }

            return FinishWithSuccess(@"calendar-access-granted", @"");
        }

        NSString *resultPath = @"";
        int firstEventArg = 1;

        if (argc >= 3 && strcmp(argv[1], "--result-file") == 0) {
            resultPath = ArgumentAt(argc, argv, 2);
            firstEventArg = 3;
        }

        if (argc - firstEventArg != 8) {
            return FinishWithError(
                @"Expected 8 arguments: title start_date start_time end_date end_time location description calendar_name.",
                resultPath,
                64
            );
        }

        NSString *title = ArgumentAt(argc, argv, firstEventArg);
        NSString *startDateText = ArgumentAt(argc, argv, firstEventArg + 1);
        NSString *startTimeText = ArgumentAt(argc, argv, firstEventArg + 2);
        NSString *endDateText = ArgumentAt(argc, argv, firstEventArg + 3);
        NSString *endTimeText = ArgumentAt(argc, argv, firstEventArg + 4);
        NSString *location = ArgumentAt(argc, argv, firstEventArg + 5);
        NSString *notes = ArgumentAt(argc, argv, firstEventArg + 6);
        NSString *calendarName = ArgumentAt(argc, argv, firstEventArg + 7);

        NSDate *startDate = ParseCalendarDate(startDateText, startTimeText);
        NSDate *endDate = ParseCalendarDate(endDateText, endTimeText);

        if (!startDate || !endDate) {
            return FinishWithError(@"Could not parse event start or end date.", resultPath, 65);
        }

        EKEventStore *store = [[EKEventStore alloc] init];
        if (!RequestCalendarAccess(store, resultPath)) {
            return 66;
        }

        EKCalendar *calendar = FindOrCreateCalendar(store, calendarName);
        if (!calendar) {
            return FinishWithError(@"Could not find or create the Email Agent calendar.", resultPath, 67);
        }

        EKEvent *event = [EKEvent eventWithEventStore:store];
        event.title = title.length ? title : @"Email event";
        event.startDate = startDate;
        event.endDate = endDate;
        event.location = location;
        event.notes = notes;
        event.calendar = calendar;

        NSError *error = nil;
        if (![store saveEvent:event span:EKSpanThisEvent commit:YES error:&error]) {
            return FinishWithError(
                [NSString stringWithFormat:@"Could not save event: %@", error.localizedDescription],
                resultPath,
                68
            );
        }

        return FinishWithSuccess(event.eventIdentifier, resultPath);
    }
}
